"""Load one protocol version from a metadata folder into the database.

Usage:  python -m apt_db.load_metadata metadata/protocol_v1

The same program loads every version. A protocol modification is just a new
folder of CSV files, so it only ever INSERTs rows - no table changes shape.

Folder contents:
  protocol.csv  study and version (one row)                      - required
  arms.csv      the arms OPEN under this version, with weights   - required
  items.csv     every form that is new or changed in this version - required
  visits.csv    new visits (usually only in version 1)            - optional
  forms.csv     new forms (usually only in version 1)             - optional
"""
import csv
import sys
from pathlib import Path

from apt_db.db import connect


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def number_or_none(text):
    return float(text) if text.strip() else None


def load_protocol(conn, folder):
    folder = Path(folder)
    p = read_csv(folder / "protocol.csv")[0]

    # 1. Study (created the first time only)
    conn.execute(
        "INSERT INTO study (study_code, title) VALUES (%s, %s) ON CONFLICT (study_code) DO NOTHING",
        (p["study_code"], p["study_title"]),
    )
    study_id = conn.execute(
        "SELECT study_id FROM study WHERE study_code = %s", (p["study_code"],)
    ).fetchone()[0]

    # 2. Protocol version - refuse to load the same version twice
    already = conn.execute(
        "SELECT 1 FROM protocol_version WHERE study_id = %s AND version_no = %s",
        (study_id, p["version_no"]),
    ).fetchone()
    if already:
        print(f"Protocol v{p['version_no']} is already loaded - nothing to do.")
        return
    pv_id = conn.execute(
        """INSERT INTO protocol_version (study_id, version_no, effective_date, description)
           VALUES (%s, %s, %s, %s) RETURNING protocol_version_id""",
        (study_id, p["version_no"], p["effective_date"], p["description"]),
    ).fetchone()[0]
    effective = p["effective_date"]

    # 3. Visits and forms (only if this version adds new ones)
    if (folder / "visits.csv").exists():
        for v in read_csv(folder / "visits.csv"):
            conn.execute(
                """INSERT INTO visit_def (study_id, visit_code, name, day_offset)
                   VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                (study_id, v["visit_code"], v["name"], v["day_offset"]),
            )
    if (folder / "forms.csv").exists():
        for f in read_csv(folder / "forms.csv"):
            conn.execute(
                """INSERT INTO form_def (study_id, visit_def_id, form_code, name)
                   SELECT %s, visit_def_id, %s, %s FROM visit_def
                   WHERE study_id = %s AND visit_code = %s
                   ON CONFLICT DO NOTHING""",
                (study_id, f["form_code"], f["name"], study_id, f["visit_code"]),
            )

    # 4. Arms: close every open arm period, then open one period per arm listed
    conn.execute(
        """UPDATE arm_period SET closed_on = %s
           WHERE closed_on IS NULL
             AND arm_id IN (SELECT arm_id FROM arm WHERE study_id = %s)""",
        (effective, study_id),
    )
    arms = read_csv(folder / "arms.csv")
    for a in arms:
        conn.execute(
            "INSERT INTO arm (study_id, arm_code, name) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            (study_id, a["arm_code"], a["name"]),
        )
        conn.execute(
            """INSERT INTO arm_period (arm_id, protocol_version_id, allocation_weight, open_from)
               SELECT arm_id, %s, %s, %s FROM arm WHERE study_id = %s AND arm_code = %s""",
            (pv_id, a["allocation_weight"], effective, study_id, a["arm_code"]),
        )

    # 5. Forms and items: one new form version per form listed in items.csv
    items = read_csv(folder / "items.csv")
    form_version_ids = {}
    for order, it in enumerate(items, start=1):
        form_code = it["form_code"]
        if form_code not in form_version_ids:
            form_version_ids[form_code] = conn.execute(
                """INSERT INTO form_version (form_def_id, protocol_version_id, version_label)
                   SELECT form_def_id, %s, %s FROM form_def WHERE study_id = %s AND form_code = %s
                   RETURNING form_version_id""",
                (pv_id, f"{form_code} v{p['version_no']}.0", study_id, form_code),
            ).fetchone()[0]

        conn.execute(
            """INSERT INTO item_def (study_id, item_code, label, data_type)
               VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING""",
            (study_id, it["item_code"], it["label"], it["data_type"]),
        )
        item_def_id = conn.execute(
            "SELECT item_def_id FROM item_def WHERE study_id = %s AND item_code = %s",
            (study_id, it["item_code"]),
        ).fetchone()[0]

        codelist_id = None
        if it["choices"].strip():  # e.g. 1=Male|2=Female
            conn.execute(
                """INSERT INTO codelist (study_id, codelist_code) VALUES (%s, %s)
                   ON CONFLICT DO NOTHING""",
                (study_id, it["item_code"]),
            )
            codelist_id = conn.execute(
                "SELECT codelist_id FROM codelist WHERE study_id = %s AND codelist_code = %s",
                (study_id, it["item_code"]),
            ).fetchone()[0]
            for sort_order, choice in enumerate(it["choices"].split("|"), start=1):
                code, decode = choice.split("=", 1)
                conn.execute(
                    """INSERT INTO codelist_item (codelist_id, code_value, decode, sort_order)
                       VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                    (codelist_id, code, decode, sort_order),
                )

        conn.execute(
            """INSERT INTO item_version (item_def_id, form_version_id, item_order, unit,
                                         range_min, range_max, required, codelist_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (item_def_id, form_version_ids[form_code], order, it["unit"] or None,
             number_or_none(it["range_min"]), number_or_none(it["range_max"]),
             it["required"] == "Y", codelist_id),
        )

    print(f"Loaded protocol v{p['version_no']} (effective {effective}): "
          f"{len(arms)} arms open ({', '.join(a['arm_code'] for a in arms)}), "
          f"{len(form_version_ids)} new form version(s), {len(items)} item version(s).")


def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: python -m apt_db.load_metadata metadata/protocol_v1")
    with connect() as conn:  # one transaction: all rows are saved, or none are
        load_protocol(conn, sys.argv[1])


if __name__ == "__main__":
    main()
