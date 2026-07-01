# ============================================================================
#  KGQA MODE (Windows / PowerShell) -- materialize each dataset to native RDF (.nt).
#  Produces datasets\<ds>\rdf\<ds>.nt files to load into your own triplestore.
#  WebQSP is NOT re-materialized (too large): its prebuilt graph is unpacked.
#  (For live virtual endpoints use start_vkgqa.ps1.)
# ============================================================================
#   .\start_kgqa.ps1              # noise + AMBROSIA + WebQSP graph
#   .\start_kgqa.ps1 noise|ambrosia|webqsp
param([string]$Target = "all")
$ErrorActionPreference = "Stop"
$HERE = Split-Path -Parent $MyInvocation.MyCommand.Path
$BENCH = Split-Path -Parent $HERE
$DATASETS = Join-Path $BENCH "datasets"
$NET = "bench_net"
$ONTOP = "ontop/ontop:5.4.0"
$JDBC = Join-Path $HERE "jdbc"
$NOISE = @("bsbm","cwd","cwe_secutable","gtfs","lubm","npd")

function Log($m){ Write-Host "[kgqa] $m" -ForegroundColor Magenta }

function Start-Backends {
  Log "starting backing databases (for materialization) ..."
  Push-Location $HERE; docker compose up -d noise_pg ambrosia_mysql; Pop-Location
  do { Start-Sleep 2 } until (docker exec bench_noise_pg pg_isready -U noise 2>$null)
  do { Start-Sleep 2 } until (docker exec bench_ambrosia_mysql mysqladmin ping -h localhost -pambrosia 2>$null)
}

function Materialize-Pg($name, $dir, $jdbcUrl) {
  $mapping  = Get-ChildItem (Join-Path $dir "mapping"),(Join-Path $dir "mappings") -Filter *.r2rml.ttl -EA SilentlyContinue | Select -First 1
  $ontology = Get-ChildItem (Join-Path $dir "ontology") -Include *.ttl,*.owl -Recurse -EA SilentlyContinue | Select -First 1
  if (-not $mapping) { Log "${name}: no mapping, skip"; return }
  $out = New-Item -ItemType Directory -Path (Join-Path $dir "rdf") -Force
  $work = New-Item -ItemType Directory -Path (Join-Path $HERE ".ontop\mat_$name") -Force
  @"
jdbc.url=$jdbcUrl
jdbc.user=noise
jdbc.password=noise
jdbc.driver=org.postgresql.Driver
"@ | Set-Content -Encoding ascii (Join-Path $work "ontop.properties")
  Copy-Item $mapping.FullName (Join-Path $work "mapping.ttl") -Force
  $oarg = @()
  if ($ontology) { Copy-Item $ontology.FullName (Join-Path $work "ontology.ttl") -Force; $oarg = @("-t","/in/ontology.ttl") }
  Log "${name}: materializing -> rdf\$name.nt"
  docker run --rm --network $NET `
    -v "$($work.FullName):/in:ro" -v "$($out.FullName):/out" `
    -v "${JDBC}:/opt/ontop/jdbc:ro" `
    $ONTOP ontop materialize -m /in/mapping.ttl @oarg -p /in/ontop.properties `
      -o "/out/$name.nt" -f ntriples 2>$null
  if (Test-Path (Join-Path $out.FullName "$name.nt")) { Log "${name}: done" } else { Log "${name}: FAILED" }
}

function Kgqa-Noise {
  foreach ($ds in $NOISE) {
    $dir = Join-Path $DATASETS $ds
    if (-not (Test-Path $dir)) { Log "skip $ds"; continue }
    Log "== $ds =="
    $zip = Join-Path $dir "data.zip"
    if ((Test-Path $zip) -and -not (Test-Path (Join-Path $dir "data"))) { Expand-Archive $zip $dir -Force }
    $exists = docker exec bench_noise_pg psql -U noise -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='$ds'"
    if ($exists -notmatch "1") { docker exec bench_noise_pg createdb -U noise $ds }
    $dump = Get-ChildItem (Join-Path $dir "data") -Filter *.sql -EA SilentlyContinue | Where-Object { $_.Name -match "postgres|$ds" } | Select -First 1
    if ($dump) { Get-Content $dump.FullName -Raw | docker exec -i bench_noise_pg psql -U noise -d $ds 2>$null | Out-Null }
    Materialize-Pg $ds $dir "jdbc:postgresql://bench_noise_pg:5432/$ds"
  }
}

function Kgqa-Webqsp {
  $gz = Get-ChildItem (Join-Path $DATASETS "webqsp\graph") -Filter *.nt.gz -EA SilentlyContinue | Select -First 1
  if (-not $gz) { Log "WebQSP graph not found -- run download_data (it is NOT materialized; too large)"; return }
  $out = New-Item -ItemType Directory -Path (Join-Path $DATASETS "webqsp\rdf") -Force
  $dst = Join-Path $out.FullName "webqsp.nt"
  Log "== WebQSP: using prebuilt graph (not materialized) =="
  if (-not (Test-Path $dst)) {
    Log "   unpacking $($gz.Name) -> rdf\webqsp.nt (668M triples, ~83 GB) ..."
    $in = [System.IO.File]::OpenRead($gz.FullName)
    $gzs = New-Object System.IO.Compression.GzipStream($in,[System.IO.Compression.CompressionMode]::Decompress)
    $outfs = [System.IO.File]::Create($dst); $gzs.CopyTo($outfs); $outfs.Close(); $gzs.Close(); $in.Close()
  }
  Log "WebQSP: rdf\webqsp.nt ready."
}

function Kgqa-Ambrosia {
  Log "== AMBROSIA: load 846 DBs + materialize (see start_kgqa.sh for the full loop) =="
  $src = Join-Path (Split-Path -Parent $BENCH) "sources\AMBROSIA\data"
  if (-not (Test-Path $src)) { Log "AMBROSIA source missing (datasets\ambrosia\DATA_ACCESS.md); skipping"; return }
  python (Join-Path $HERE "load\load_ambrosia.py")
  $out = New-Item -ItemType Directory -Path (Join-Path $DATASETS "ambrosia\rdf") -Force
  Set-Content -Path (Join-Path $out.FullName "ambrosia.nt") -Value "" -NoNewline
  $ontoDir = Join-Path $DATASETS "ambrosia\ontology"
  $n = 0
  Get-ChildItem (Join-Path $DATASETS "ambrosia\mappings") -Recurse -Filter *.r2rml.ttl | Sort-Object FullName | ForEach-Object {
    $base = $_.BaseName -replace '\.r2rml$',''
    $domain = Split-Path -Leaf $_.DirectoryName
    $onto = Join-Path $ontoDir ("{0}.ttl" -f $domain.ToLower())
    $work = New-Item -ItemType Directory -Path (Join-Path $HERE ".ontop\mat_amb_$base") -Force
    @"
jdbc.url=jdbc:mysql://bench_ambrosia_mysql:3306/amb_${base}?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC
jdbc.user=ambrosia
jdbc.password=ambrosia
jdbc.driver=com.mysql.cj.jdbc.Driver
"@ | Set-Content -Encoding ascii (Join-Path $work "ontop.properties")
    Copy-Item $_.FullName (Join-Path $work "mapping.ttl") -Force
    $oarg = @(); if (Test-Path $onto) { Copy-Item $onto (Join-Path $work "ontology.ttl") -Force; $oarg = @("-t","/in/ontology.ttl") }
    docker run --rm --network $NET -v "$($work.FullName):/in:ro" -v "$($work.FullName):/out" -v "${JDBC}:/opt/ontop/jdbc:ro" `
      $ONTOP ontop materialize -m /in/mapping.ttl @oarg -p /in/ontop.properties -o /out/part.nt -f ntriples 2>$null
    $part = Join-Path $work.FullName "part.nt"
    if (Test-Path $part) { Get-Content $part | Add-Content (Join-Path $out.FullName "ambrosia.nt") }
    Remove-Item $work -Recurse -Force; $n++
    if ($n % 50 -eq 0) { Log "   ...$n/846" }
  }
  Log "AMBROSIA: $n DBs -> rdf\ambrosia.nt"
}

Start-Backends
switch ($Target) {
  "all"      { Kgqa-Noise; Kgqa-Ambrosia; Kgqa-Webqsp }
  "noise"    { Kgqa-Noise }
  "ambrosia" { Kgqa-Ambrosia }
  "webqsp"   { Kgqa-Webqsp }
  default    { Write-Host "usage: .\start_kgqa.ps1 [all|noise|ambrosia|webqsp]"; exit 1 }
}
Log "done. RDF graphs in datasets\<ds>\rdf\*.nt -- load them into your triplestore."
