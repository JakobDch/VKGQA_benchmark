#!/usr/bin/env python3
"""Load all AMBROSIA databases (SQLite source) into the benchmark MySQL container.

Each AMBROSIA case ships as a .sqlite file. We read its schema+rows and recreate it
as a MySQL schema `amb_<db_base>` in bench_ambrosia_mysql, so the canonical R2RML
mappings (which target MySQL) resolve.

Reads directly from sources/AMBROSIA/data (NOT redistributed — user must obtain it;
see datasets/ambrosia/DATA_ACCESS.md). Idempotent: skips schemas that already have tables.

Usage:
  python load/load_ambrosia.py                 # all
  python load/load_ambrosia.py <db_base> ...   # only named cases
Requires: mysql-connector-python (pip install mysql-connector-python) and the
bench_ambrosia_mysql container running (start_vkgqa.sh brings it up).
"""
import os, sys, glob, sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.abspath(os.path.join(HERE, "..", ".."))
SRC = os.path.join(BENCH, "..", "sources", "AMBROSIA", "data")
MYSQL = dict(host="127.0.0.1", port=3307, user="ambrosia", password="ambrosia")

SQLITE_TO_MYSQL = {  # crude type map; AMBROSIA only uses INTEGER/TEXT/REAL
    "INTEGER": "BIGINT", "INT": "BIGINT", "REAL": "DOUBLE",
    "TEXT": "LONGTEXT", "": "LONGTEXT",
}

def mysql_type(sqlite_type):
    t = (sqlite_type or "").upper().split("(")[0].strip()
    return SQLITE_TO_MYSQL.get(t, "LONGTEXT")

def main():
    try:
        import mysql.connector
    except ImportError:
        sys.exit("pip install mysql-connector-python first")
    if not os.path.isdir(SRC):
        sys.exit(f"AMBROSIA source not found at {SRC} (see datasets/ambrosia/DATA_ACCESS.md)")
    want = set(sys.argv[1:])
    files = sorted(glob.glob(os.path.join(SRC, "**", "*.sqlite"), recursive=True))
    cx = mysql.connector.connect(**MYSQL)
    cur = cx.cursor()
    done = 0
    for sf in files:
        base = os.path.basename(sf)[:-len(".sqlite")]
        if want and base not in want:
            continue
        schema = "amb_" + base
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{schema}`")
        cur.execute(f"USE `{schema}`")
        cur.execute("SHOW TABLES")
        if cur.fetchall():          # already loaded
            continue
        sc = sqlite3.connect(sf); sc.row_factory = sqlite3.Row
        tabs = [r[0] for r in sc.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        for t in tabs:
            cols = sc.execute(f'PRAGMA table_info("{t}")').fetchall()
            defs = ", ".join(f'`{c["name"]}` {mysql_type(c["type"])}' for c in cols)
            cur.execute(f'CREATE TABLE `{t}` ({defs})')
            rows = sc.execute(f'SELECT * FROM "{t}"').fetchall()
            if rows:
                ph = ", ".join(["%s"] * len(cols))
                cn = ", ".join(f'`{c["name"]}`' for c in cols)
                cur.executemany(f'INSERT INTO `{t}` ({cn}) VALUES ({ph})',
                                [tuple(r) for r in rows])
        cx.commit(); sc.close()
        done += 1
        if done % 50 == 0:
            print(f"  loaded {done} schemas ...", flush=True)
    cur.close(); cx.close()
    print(f"AMBROSIA: {done} schemas loaded into MySQL.")

if __name__ == "__main__":
    main()
