"""Build one analysis-friendly "wide" view per form, generated from the metadata.

Usage:  python -m apt_db.views

Storage stays long (one row per answer). These views turn it back into one row per
completed form, with one column per question that has ever appeared on any version of
that form. Re-run after a protocol modification: the views gain the new columns,
while the tables underneath never change.
"""
from apt_db.db import connect

VALUE_COLUMN = {"int": "value_num", "real": "value_num", "date": "value_date",
                "code": "value_text", "text": "value_text"}


def build_views(conn):
    forms = conn.execute("SELECT form_def_id, form_code FROM form_def ORDER BY form_def_id").fetchall()
    for form_def_id, form_code in forms:
        items = conn.execute(
            """SELECT idf.item_code, idf.data_type, min(iv.item_order) AS first_order
               FROM item_version iv
               JOIN item_def idf USING (item_def_id)
               JOIN form_version fv USING (form_version_id)
               WHERE fv.form_def_id = %s
               GROUP BY idf.item_code, idf.data_type
               ORDER BY first_order""",
            (form_def_id,),
        ).fetchall()
        # One column per question: pick that question's answer out of the long rows
        columns = ",\n       ".join(
            f"max(d.{VALUE_COLUMN[data_type]}) FILTER (WHERE i.item_code = '{code}') AS {code}"
            for code, data_type, _ in items
        )
        view = f"v_{form_code}_wide"
        conn.execute(f"DROP VIEW IF EXISTS {view}")
        conn.execute(f"""
CREATE VIEW {view} AS
SELECT p.participant_id, s.site_code, a.arm_code, vi.visit_date, fv.version_label AS form_version,
       {columns}
FROM form_instance fi
JOIN form_version fv ON fv.form_version_id = fi.form_version_id
JOIN visit_instance vi USING (visit_instance_id)
JOIN participant p USING (participant_id)
JOIN site s USING (site_id)
JOIN randomisation r USING (participant_id)
JOIN arm a ON a.arm_id = r.arm_id
LEFT JOIN item_data d ON d.form_instance_id = fi.form_instance_id
LEFT JOIN item_version iv ON iv.item_version_id = d.item_version_id
LEFT JOIN item_def i ON i.item_def_id = iv.item_def_id
WHERE fv.form_def_id = {int(form_def_id)}
GROUP BY fi.form_instance_id, p.participant_id, s.site_code, a.arm_code, vi.visit_date, fv.version_label""")
        print(f"{view}: {len(items)} question columns ({', '.join(c for c, _, _ in items)})")


def main():
    with connect() as conn:
        build_views(conn)


if __name__ == "__main__":
    main()