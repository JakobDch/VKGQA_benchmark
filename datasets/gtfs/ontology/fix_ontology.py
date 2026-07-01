#!/usr/bin/env python3
"""Make the shipped GTFS vocabulary (gtfs.ttl) consistent with the R2RML mapping so
Ontop can load it as an OWL2QL TBox for a full VKG (no bootstrapping / mapping-only).

The official GTFS vocabulary has three families of defects w.r.t. how gtfs.r2rml.ttl
actually uses each term (verified by inspecting rr:column vs rr:template/parent in the
mapping):

  (1) PUNNING  — gtfs:block declared as BOTH owl:ObjectProperty and owl:DatatypeProperty.
                 Mapping uses it on rr:column "block_id" (literal) -> keep Datatype, drop Object.
  (2) BAD RANGE — data properties whose rdfs:range is *another property* (foaf:name,
                 foaf:page, foaf:phone, schema:startDate/endDate/version, geo:lat/long)
                 instead of a literal datatype. Repointed to the right xsd: type.
  (3) OBJ-VS-DATA — gtfs:zone, gtfs:direction and the 7 weekday flags (monday..sunday)
                 declared owl:ObjectProperty but mapped to rr:column (literals).
                 Flipped to owl:DatatypeProperty.

(1) and (2) are applied by hand-edits already present in gtfs.ttl (commented FIX lines);
this script applies (3) idempotently and is safe to re-run. It edits gtfs.ttl in place.
"""
import re, pathlib

TTL = pathlib.Path(__file__).with_name("gtfs.ttl")
text = TTL.read_text(encoding="utf-8")

# (3) flip the 9 literal-valued properties from ObjectProperty to DatatypeProperty
FLIP = ["zone", "direction", "monday", "tuesday", "wednesday", "thursday",
        "friday", "saturday", "sunday"]
n = 0
for p in FLIP:
    pat = re.compile(rf"(^gtfs:{p} rdf:type )owl:ObjectProperty( ;)", re.M)
    text, c = pat.subn(
        rf"\1owl:DatatypeProperty\2  # FIX: mapped to a literal column, not an IRI", text)
    n += c

# (3b) the flipped properties carry CLASS-valued ranges (skos:Concept enum for the
# weekdays, gtfs:Zone for zone) meant for the object-property reading. As datatype
# properties over literal columns they need an xsd: range instead. Replace each
# property's rdfs:range (which may be a bracket-balanced blank node) with the literal
# type implied by its column: weekday/direction = INT 0/1 -> xsd:integer; zone = VARCHAR.
# Ranges must match the rr:datatype the mapping casts each column to: the 7 weekday
# flags are cast to xsd:boolean in gtfs.r2rml.ttl; zone_id is a VARCHAR (string);
# direction_id has no explicit cast (integer column).
LITRANGE = {"zone": "xsd:string", "direction": "xsd:integer",
            "monday": "xsd:boolean", "tuesday": "xsd:boolean", "wednesday": "xsd:boolean",
            "thursday": "xsd:boolean", "friday": "xsd:boolean", "saturday": "xsd:boolean",
            "sunday": "xsd:boolean"}

def replace_range_for(prop: str, newrange: str, s: str) -> tuple[str, int]:
    """Replace the rdfs:range object inside the declaration block of gtfs:<prop>.
    Handles both 'rdfs:range gtfs:Zone ;' and a bracket-balanced 'rdfs:range [ ... ] ;'."""
    start = s.find(f"gtfs:{prop} rdf:type ")
    if start < 0:
        return s, 0
    # bound the block at the terminating ' .' of this declaration
    end = s.find("\n\n", start)
    block = s[start:end]
    rs = block.find("rdfs:range")
    if rs < 0:
        return s, 0
    j = rs + len("rdfs:range")
    while block[j] in " \t":
        j += 1
    if block[j] == "[":
        depth = 0
        k = j
        while k < len(block):
            if block[k] == "[":
                depth += 1
            elif block[k] == "]":
                depth -= 1
                if depth == 0:
                    k += 1
                    break
            k += 1
        obj_end = k
    else:  # simple IRI/prefixed-name token up to ' ;'
        obj_end = block.find(";", j)
    new_block = block[:rs] + f"rdfs:range {newrange} " + block[obj_end:].lstrip()
    return s[:start] + new_block + s[end:], 1

# (3c) datatype-property ranges that Ontop rejects because the mapping casts the column
# to a DIFFERENT (but compatible) xsd type — Ontop requires an exact match, not a subtype.
# Align the TBox range to the mapping's rr:datatype cast.
#   distanceTraveled: tbox gtfs:nonNegativeFloat (non-standard) vs mapping xsd:double
#   headwaySeconds:   tbox xsd:positiveInteger    vs mapping xsd:integer
#   stopSequence:     tbox xsd:nonNegativeInteger vs mapping xsd:integer
LITRANGE.update({"distanceTraveled": "xsd:double",
                 "headwaySeconds": "xsd:integer",
                 "stopSequence": "xsd:integer"})

# (3e) the four GTFS time properties (arrival/departure/start/endTime) are ranged on
# schema:Time / schema:startTime / schema:endTime — these are classes/properties, which
# (a) makes Ontop PUN them as both data+object and (b) clashes with the column type:
# GTFS stores times as VARCHAR strings ("25:30:00" is legal, >24h), so Ontop infers
# xsd:string. Set the range to xsd:string, which fixes both the punning and the type.
LITRANGE.update({"arrivalTime": "xsd:string", "departureTime": "xsd:string",
                 "startTime": "xsd:string", "endTime": "xsd:string"})

r = 0
for prop, rng in LITRANGE.items():
    text, c = replace_range_for(prop, rng, text)
    r += c

# (3d) NARROWED NUMERIC RANGES. Ontop infers a column's xsd type from the SQL type
# (INT -> xsd:integer, DECIMAL/REAL -> xsd:decimal/double) and requires the TBox range
# to match EXACTLY — it will not accept a subtype. The GTFS vocabulary uses narrowed
# numeric ranges (xsd:nonNegativeInteger, xsd:positiveInteger, xsd:float) and the
# non-standard gtfs:nonNegativeFloat. Normalise every such range to the base type Ontop
# infers, so the constraint is satisfied without weakening the data (the column values
# are unchanged; only the declared XSD bound is relaxed to the inferred base type).
NUM_NORM = {
    "xsd:nonNegativeInteger": "xsd:integer", "xsd:positiveInteger": "xsd:integer",
    "xsd:negativeInteger": "xsd:integer", "xsd:nonPositiveInteger": "xsd:integer",
    "xsd:short": "xsd:integer", "xsd:long": "xsd:integer", "xsd:byte": "xsd:integer",
    "xsd:unsignedInt": "xsd:integer",
    "xsd:float": "xsd:double", "gtfs:nonNegativeFloat": "xsd:double",
}
nn = 0
for narrow, base in NUM_NORM.items():
    text, c = re.subn(rf"(rdfs:range\s+){re.escape(narrow)}(\s*;)",
                      rf"\1{base}\2  # FIX: narrowed numeric range relaxed to Ontop-inferred base type",
                      text)
    nn += c

# (3f) URL properties used as IRIs in the mapping. gtfs:fareUrl / gtfs:routeUrl carry
# rr:termType rr:IRI on their column in gtfs.r2rml.ttl (the value IS an IRI), so they
# must be OBJECT properties, not datatype properties. (gtfs:url, gtfs:routeUrl etc.)
# fareUrl is mis-declared as DatatypeProperty with an xsd range; routeUrl is undeclared.
# Make both ObjectProperty and drop any xsd range (object props range over IRIs).
# gtfs:fareUrl's declaration spans a multi-line comment block (with dots in URLs), so a
# greedy/lazy regex across the block is unreliable. Operate on the declaration block,
# bounded by the gtfs:fareUrl start and the terminating ' .' line.
fu = text.find("gtfs:fareUrl rdfs:comment")
if fu < 0:
    fu = text.find("gtfs:fareUrl rdf:type")
if fu >= 0:
    fu_end = text.find(" .\n", fu)
    blk = text[fu:fu_end]
    blk = blk.replace("rdf:type owl:DatatypeProperty ;",
                      "rdf:type owl:ObjectProperty ;  # FIX: column typed rr:IRI in mapping")
    blk = re.sub(r"\n\s*rdfs:range xsd:anyURI[^\n;]*;", "", blk)  # object props range over IRIs
    text = text[:fu] + blk + text[fu_end:]
if "gtfs:routeUrl rdf:type" not in text:
    # append a minimal correct declaration near the other route properties
    text = text.rstrip() + (
        "\n\n###  http://vocab.gtfs.org/terms#routeUrl  (added: undeclared in source vocab; "
        "mapping types it rr:IRI)\n"
        "gtfs:routeUrl rdf:type owl:ObjectProperty ;\n"
        "              rdfs:domain gtfs:Route ;\n"
        '              rdfs:label "route URL"@en .\n')

TTL.write_text(text, encoding="utf-8")
print(f"flipped {n} ObjectProperty->DatatypeProperty declarations; repointed {r} class-ranges; "
      f"normalised {nn} narrowed numeric ranges; fixed URL object-properties")
