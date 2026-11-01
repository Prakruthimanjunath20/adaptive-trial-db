"""Create or verify a frozen, reproducible interim data cut.

Usage:
  python -m apt_db.datacut create IA1 2026-05-14   # freeze the data, export data/cuts/IA1.csv, store its SHA-256
  python -m apt_db.datacut verify IA1              # re-export the frozen copy and compare fingerprints

The cut includes participants randomised on or before the cut-off date, and only visits
on or before that date. The frozen copy lives in data_cut_item, so later corrections to the
live data never change a cut that has already been sent to the DMC.
"""
import csv
import hashlib
import io
import sys
from pathlib import Path

from apt_db.db import connect

COLUMNS = ["participant_id", "site_code", "arm_code", "protocol_version", "randomised_at",
           "visit_code", "visit_date", "form_version", "item_code", "value"]
OUT_DIR = Path("data/cuts")


def export_csv(conn, cut_id):
    """The frozen rows as CSV text, in a fixed order so the same data always gives the same bytes."""
    rows = conn.execute(
        f"""SELECT {", ".join(COLUMNS)} FROM data_cut_item WHERE cut_id = %s
            ORDER BY participant_id, visit_date, form_version, item_code""",
        (cut_id,),
    ).fetchall()
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(COLUMNS)
    writer.writerows(rows)
    return buf.getvalue(), len(rows)


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def create(conn, cut_code, cut_date):
    cut_id = conn.execute(
        "INSERT INTO data_cut (cut_code, cut_date) VALUES (%s, %s) RETURNING cut_id", (cut_code, cut_date)
    ).fetchone()[0]
    conn.execute(
        """INSERT INTO data_cut_item
           SELECT %s, p.participant_id, s.site_code, a.arm_code, pv.version_no, r.randomised_at,
                  vd.visit_code, vi.visit_date, fv.version_label, idf.item_code,
                  coalesce(d.value_num::text, d.value_text, d.value_date::text)
           FROM item_data d
           JOIN item_version iv USING (item_version_id)
           JOIN item_def idf USING (item_def_id)
           JOIN form_instance fi USING (form_instance_id)
           JOIN form_version fv ON fv.form_version_id = fi.form_version_id
           JOIN visit_instance vi USING (visit_instance_id)
           JOIN visit_def vd USING (visit_def_id)
           JOIN participant p USING (participant_id)
           JOIN site s USING (site_id)
           JOIN randomisation r USING (participant_id)
           JOIN arm a ON a.arm_id = r.arm_id
           JOIN protocol_version pv ON pv.protocol_version_id = r.protocol_version_id
           WHERE r.randomised_at <= %s AND vi.visit_date <= %s""",
        (cut_id, cut_date, cut_date),
    )
    text, n = export_csv(conn, cut_id)
    digest = sha256(text)
    conn.execute("UPDATE data_cut SET row_count = %s, sha256 = %s WHERE cut_id = %s", (n, digest, cut_id))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{cut_code}.csv").write_text(text, encoding="utf-8")
    print(f"{cut_code}: cut-off {cut_date}, {n} rows -> {OUT_DIR / (cut_code + '.csv')}")
    print(f"SHA-256 {digest}")


def verify(conn, cut_code):
    found = conn.execute("SELECT cut_id, sha256 FROM data_cut WHERE cut_code = %s", (cut_code,)).fetchone()
    if found is None:
        sys.exit(f"No data cut called {cut_code}.")
    cut_id, stored = found
    text, n = export_csv(conn, cut_id)
    again = sha256(text)
    print(f"{cut_code}: stored   SHA-256 {stored}")
    print(f"{cut_code}: re-export SHA-256 {again}")
    print("IDENTICAL - the cut is reproducible" if again == stored else "DIFFERENT - investigate!")
    return again == stored


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "create":
        with connect() as conn:
            create(conn, sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 3 and sys.argv[1] == "verify":
        with connect() as conn:
            ok = verify(conn, sys.argv[2])
        sys.exit(0 if ok else 1)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
