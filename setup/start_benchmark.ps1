# One-command setup for the Ambiguity VKGQA benchmark (Windows / PowerShell).
#   .\start_benchmark.ps1              # backends + load all + start endpoints
#   .\start_benchmark.ps1 noise|ambrosia|webqsp
# Requires Docker Desktop. All services bind to 127.0.0.1 only.
param([string]$Target = "all")
$ErrorActionPreference = "Stop"
$HERE = Split-Path -Parent $MyInvocation.MyCommand.Path
$BENCH = Split-Path -Parent $HERE
$DATASETS = Join-Path $BENCH "datasets"
$NET = "bench_net"
$ONTOP = "ontop/ontop:5.4.0"
$NOISE = @("bsbm","cwd","cwe_secutable","gtfs","lubm","npd")

function Log($m){ Write-Host "[bench] $m" -ForegroundColor Cyan }

function Start-Backends {
  Log "starting backing services (postgres / mysql / virtuoso) ..."
  docker compose -f (Join-Path $HERE "docker-compose.yml") up -d
  Log "waiting for postgres ..."
  do { Start-Sleep 2 } until (docker exec bench_noise_pg pg_isready -U noise 2>$null)
  Log "waiting for mysql ..."
  do { Start-Sleep 2 } until (docker exec bench_ambrosia_mysql mysqladmin ping -h localhost -pambrosia 2>$null)
  Log "backends up."
}

function Load-Noise {
  $i = 0
  foreach ($ds in $NOISE) {
    $dir = Join-Path $DATASETS $ds
    if (-not (Test-Path $dir)) { Log "skip $ds"; continue }
    Log "== noise: $ds =="
    $zip = Join-Path $dir "data.zip"
    if ((Test-Path $zip) -and -not (Test-Path (Join-Path $dir "data"))) {
      Expand-Archive -Path $zip -DestinationPath $dir -Force
    }
    $exists = docker exec bench_noise_pg psql -U noise -d postgres -tc "SELECT 1 FROM pg_database WHERE datname='$ds'"
    if ($exists -notmatch "1") { docker exec bench_noise_pg createdb -U noise $ds }
    $dump = Get-ChildItem -Path (Join-Path $dir "data") -Filter *.sql -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match "postgres|$ds" } | Select-Object -First 1
    if ($dump) {
      Log "   loading $($dump.Name) -> $ds"
      Get-Content $dump.FullName -Raw | docker exec -i bench_noise_pg psql -U noise -d $ds 2>$null | Out-Null
    } else { Log "   (warn: no postgres dump for $ds)" }
    Start-OntopPg $ds $dir (13001 + $i); $i++
  }
}

function Start-OntopPg($ds, $dir, $port) {
  $mapping  = Get-ChildItem (Join-Path $dir "mapping") -Filter *.r2rml.ttl -EA SilentlyContinue | Select -First 1
  $ontology = Get-ChildItem (Join-Path $dir "ontology") -Include *.ttl,*.owl -Recurse -EA SilentlyContinue | Select -First 1
  if (-not $mapping) { Log "   (no mapping for $ds)"; return }
  $work = New-Item -ItemType Directory -Path (Join-Path $HERE ".ontop\$ds") -Force
  @"
jdbc.url=jdbc:postgresql://bench_noise_pg:5432/$ds
jdbc.user=noise
jdbc.password=noise
jdbc.driver=org.postgresql.Driver
"@ | Set-Content -Encoding ascii (Join-Path $work "ontop.properties")
  Copy-Item $mapping.FullName (Join-Path $work "mapping.ttl") -Force
  $ontoArg = @()
  if ($ontology) { Copy-Item $ontology.FullName (Join-Path $work "ontology.ttl") -Force
                   $ontoArg = @("-t","/opt/ontop/input/ontology.ttl") }
  $jdbc = Join-Path $HERE "jdbc"
  docker rm -f "bench_ontop_$ds" 2>$null | Out-Null
  docker run -d --name "bench_ontop_$ds" --network $NET `
    -p "127.0.0.1:${port}:8080" `
    -v "$($work.FullName):/opt/ontop/input:ro" `
    -v "${jdbc}:/opt/ontop/jdbc:ro" `
    $ONTOP ontop endpoint `
    -m /opt/ontop/input/mapping.ttl @ontoArg -p /opt/ontop/input/ontop.properties | Out-Null
  Log "   $ds SPARQL -> http://localhost:$port/sparql"
}

function Load-Webqsp {
  Log "== WebQSP: bulk-loading shipped 668M RDF into Virtuoso =="
  $gz = Get-ChildItem (Join-Path $DATASETS "webqsp\graph") -Filter *.nt.gz -EA SilentlyContinue | Select -First 1
  if (-not $gz) { Log "   no RDF graph found (see DATA_ACCESS.md)"; return }
  Log "   loading $($gz.Name) (takes a while for 668M triples) ..."
  docker exec bench_webqsp_store bash -lc "cd /graph && for f in *.nt.gz; do [ -f `"`${f%.gz}`" ] || gunzip -k `"`$f`"; done"
  docker exec bench_webqsp_store isql 1111 dba dba "exec=ld_dir('/graph','*.nt','http://rdf.freebase.com/');" 2>$null
  docker exec bench_webqsp_store isql 1111 dba dba "exec=rdf_loader_run();" 2>$null
  docker exec bench_webqsp_store isql 1111 dba dba "exec=checkpoint;" 2>$null
  Log "   WebQSP SPARQL -> http://localhost:8890/sparql"
}

function Load-Ambrosia {
  Log "== AMBROSIA: creating MySQL schemas + loading (via load/load_ambrosia.py) =="
  $src = Join-Path (Split-Path -Parent $BENCH) "sources\AMBROSIA\data"
  if (-not (Test-Path $src)) { Log "   AMBROSIA source missing (see datasets/ambrosia/DATA_ACCESS.md)"; return }
  python (Join-Path $HERE "load\load_ambrosia.py")
  Log "   start a per-DB endpoint with: .\run_ontop_ambrosia.ps1 <db_base> <port>"
}

Start-Backends
switch ($Target) {
  "all"      { Load-Noise; Load-Ambrosia; Load-Webqsp }
  "noise"    { Load-Noise }
  "ambrosia" { Load-Ambrosia }
  "webqsp"   { Load-Webqsp }
  default    { Write-Host "usage: .\start_benchmark.ps1 [all|noise|ambrosia|webqsp]"; exit 1 }
}
Log "done. 'docker ps' shows running endpoints."
