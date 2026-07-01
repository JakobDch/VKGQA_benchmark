#!/usr/bin/env python3
"""
Generate a COMPLETE Ontop OBDA mapping for one AMBROSIA DB.

"Complete" = every table -> a class; every non-PK column -> a datatype property;
every FK -> an object property; the PK builds the row IRI. This guarantees any SQL
projection/join/filter over the DB has a SPARQL equivalent.

Canonicalization (synonym resolution) is driven by the domain's canonical.json:
  {
    "namespace": "http://ambrosia.example.org/agriculture#",
    "classes":    { "Farm": ["Farms","FarmerInfo",...], ... },   # raw table -> canonical class
    "properties": { "name": ["Name","name","farm_name",...], ... } # raw column -> canonical prop
  }
Any table/column not listed falls back to a sanitized version of its own name
(so the mapping is always complete even before full manual curation).

For composite-PK / link tables (no single PK or PK = all FKs), we still emit a
class + a blank-ish IRI from the concatenated key, and the FK object properties.
"""
import sqlite3, os, sys, json, re, argparse
from collections import defaultdict

def sanitize_local(name):
    s = re.sub(r'[^0-9a-zA-Z_]', '_', name)
    s = re.sub(r'_+', '_', s).strip('_')
    if not s:
        s = "x"
    if re.match(r'^[0-9]', s):
        s = "n_" + s
    return s

def load_canonical(path):
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}

def build_lookups(canon):
    """raw_name(lower) -> canonical for classes and properties."""
    cls = {}
    for canonical, raws in canon.get("classes", {}).items():
        for r in raws:
            cls[r.lower()] = canonical
    prop = {}
    for canonical, raws in canon.get("properties", {}).items():
        for r in raws:
            prop[r.lower()] = canonical
    return cls, prop

def canonical_class(table, cls_lookup):
    return cls_lookup.get(table.lower(), sanitize_local(table))

def canonical_prop(col, prop_lookup):
    return prop_lookup.get(col.lower(), sanitize_local(col))

# Derived (computed) datatype properties injected into a table's base mapping so that
# computations SPARQL cannot express (e.g. date-duration arithmetic, which Ontop will not
# push to SQL) are done once, in the R2RML SQL view, and exposed as a plain typed literal.
# Keyed by db base name -> { table -> [(prop, sql_expr, xsd_type), ...] }.
# The SQL expression must be valid MySQL and reference only that table's columns.
DERIVED_COLUMNS = {
    "vague_2cols_maintenance_cost": {
        # JULIANDAY(End)-JULIANDAY(Start) in gold SQL -> integer day-count; xsd:integer so
        # SPARQL can MAX/compare numerically (Ontop does not compute xsd:date subtraction).
        "Project": [("durationDays", "DATEDIFF(`EndDate`,`StartDate`)", "xsd:integer")],
    },
}


def generate(sqlite_path, canon_path, schema_name=None):
    _db_base = os.path.splitext(os.path.basename(sqlite_path))[0]
    _derived = DERIVED_COLUMNS.get(_db_base, {})
    canon = load_canonical(canon_path)
    ns = canon.get("namespace", "http://ambrosia.example.org/" +
                   sanitize_local(os.path.basename(os.path.dirname(canon_path or "x"))).lower() + "#")
    cls_lookup, prop_lookup = build_lookups(canon)

    con = sqlite3.connect(sqlite_path); cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [r[0] for r in cur.fetchall()]

    meta = {}
    for t in tables:
        cur.execute('PRAGMA table_info("%s")' % t)
        cols = cur.fetchall()  # cid,name,type,notnull,dflt,pk
        cur.execute('PRAGMA foreign_key_list("%s")' % t)
        fks = cur.fetchall()   # id,seq,table,from,to,...
        pk = [c[1] for c in cols if c[5]]
        meta[t] = dict(cols=cols, fks=fks, pk=pk)
    con.close()

    def row_keys(t):
        """Identity columns for the row IRI. PK if present; else the migration added a
        surrogate `_amb_rowid` (stable, non-null) which we use — AMBROSIA no-PK tables
        often have NULL/non-unique key columns that otherwise collapse the entity."""
        m = meta[t]
        if m["pk"]:
            return m["pk"]
        return ["_amb_rowid"]

    def iri_template(t):
        cls = canonical_class(t, cls_lookup)
        keys = row_keys(t)
        key_expr = "/".join("{%s}" % k for k in keys)
        return f"ex:{cls}/{key_expr}", cls

    lines = []
    prop_ns = ns.rstrip("#") + "/prop#"
    lines.append("[PrefixDeclaration]")
    lines.append(f":\t{ns}")
    lines.append(f"p:\t{prop_ns}")
    lines.append(f"ex:\t{ns.rstrip('#')}/id/")
    lines.append("rdf:\thttp://www.w3.org/1999/02/22-rdf-syntax-ns#")
    lines.append("xsd:\thttp://www.w3.org/2001/XMLSchema#")
    lines.append("")
    lines.append("[MappingDeclaration] @collection [[")

    def has_surrogate(t):
        return not meta[t]["pk"]

    for t in tables:
        m = meta[t]
        templ, cls = iri_template(t)
        fk_cols = {f[3] for f in m["fks"]}
        # class + datatype properties (non-FK, all columns become props; PK too if not surrogate)
        select_cols = [c[1] for c in m["cols"]]
        if has_surrogate(t):
            select_cols = ["_amb_rowid"] + select_cols
        col_list = ", ".join("`%s`" % c for c in select_cols)
        # main triples: type + a datatype property for EVERY column (including FK and
        # key columns) so their literal values are queryable; FK columns ALSO get an
        # object property below. (Without the datatype prop, SQL that selects/filters a
        # FK or composite-key column has no SPARQL equivalent.)
        dt_props = []
        for c in m["cols"]:
            cname = c[1]
            prop = canonical_prop(cname, prop_lookup)
            dt_props.append(f"p:{prop} {{{cname}}}")
        # derived/computed properties for this table (done in SQL, typed explicitly)
        derived = _derived.get(t, [])
        derived_select = ""
        for prop, expr, xtype in derived:
            dt_props.append(f"p:{prop} {{{prop}}}^^{xtype}")
            derived_select += f", {expr} AS `{prop}`"
        target = f"{templ} a :{cls}"
        if dt_props:
            target += " ; " + " ; ".join(dt_props)
        target += " ."
        lines.append(f"mappingId\t{sanitize_local(t)}_base")
        lines.append(f"target\t\t{target}")
        lines.append(f"source\t\tSELECT {col_list}{derived_select} FROM `{t}`")
        lines.append("")

        # count DISTINCT FK columns per referenced table (dedupe duplicate FK rows that
        # AMBROSIA schemas sometimes declare, e.g. fleetId->Fleets listed twice)
        _ref_cols = {}
        for _f in m["fks"]:
            _ref_cols.setdefault(_f[2], set()).add(_f[3])
        _ref_counts = {rt: len(cols) for rt, cols in _ref_cols.items()}
        # FK object properties
        for fid, seq, rtable, ffrom, fto, *_ in m["fks"]:
            if rtable not in meta:
                continue
            r_templ, r_cls = iri_template(rtable)
            # build target referencing the FK column value placed into the ref template
            ref_keys = meta[rtable]["pk"] if meta[rtable]["pk"] else [fto]
            # object property: has<RefClass>; if >1 FK to same table, suffix with FK column
            opname = "p:has" + r_cls
            if _ref_counts.get(rtable, 0) > 1:
                opname += "_" + sanitize_local(ffrom)
            # the ref IRI: substitute the ref PK with our FK column; works for single-key refs
            if len(ref_keys) == 1:
                ref_iri = f"ex:{r_cls}/{{{ffrom}}}"
            else:
                # composite: can't cleanly express; skip (rare for AMBROSIA link targets)
                continue
            lines.append(f"mappingId\t{sanitize_local(t)}_{sanitize_local(ffrom)}_fk")
            lines.append(f"target\t\t{templ} {opname} {ref_iri} .")
            src_cols = list(dict.fromkeys(row_keys(t) + [ffrom]))
            lines.append(f"source\t\tSELECT {', '.join('`%s`'%c for c in src_cols)} FROM `{t}` WHERE `{ffrom}` IS NOT NULL")
            lines.append("")

    lines.append("]]")
    return ns, "\n".join(lines) + "\n", meta

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("sqlite_path")
    ap.add_argument("--canonical", help="path to domain canonical.json")
    ap.add_argument("-o", "--out")
    args = ap.parse_args()
    ns, obda, meta = generate(args.sqlite_path, args.canonical)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(obda)
        print("wrote", args.out)
    else:
        sys.stdout.write(obda)
