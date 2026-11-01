"""Correct one answer, with a mandatory reason for change (recorded in the audit trail).

Usage:  python -m apt_db.correct S01-0006 BASELINE sbp 108 "Query Q-0012: site corrected SBP from 1080 to 108"
"""
import sys

from apt_db.db import connect


def correct(conn, participant_id, visit_code, item_code, new_value, reason):
    row = conn.execute(
        """SELECT d.item_data_id, idf.data_type, coalesce(d.value_num::text, d.value_text, d.value_date::text)
           FROM item_data d
           JOIN item_version iv USING (item_version_id)
           JOIN item_def idf USING (item_def_id)
           JOIN form_instance fi USING (form_instance_id)
           JOIN visit_instance vi USING (visit_instance_id)
           JOIN visit_def vd USING (visit_def_id)
           WHERE vi.participant_id = %s AND vd.visit_code = %s AND idf.item_code = %s""",
        (participant_id, visit_code, item_code),
    ).fetchone()
    if row is None:
        sys.exit(f"No {item_code} answer found for {participant_id} at {visit_code}.")
    item_data_id, data_type, old_value = row
    column = {"int": "value_num", "real": "value_num", "date": "value_date"}.get(data_type, "value_text")

    # The reason only lives for this transaction; the audit trigger copies it into audit_log
    conn.execute("SELECT set_config('app.change_reason', %s, true)", (reason,))
    conn.execute(f"UPDATE item_data SET {column} = %s WHERE item_data_id = %s", (new_value, item_data_id))
    print(f"{participant_id} {visit_code} {item_code}: {old_value} -> {new_value}  (reason: {reason})")


def main():
    if len(sys.argv) != 6:
        sys.exit(__doc__)
    with connect() as conn:  # one transaction
        correct(conn, *sys.argv[1:])


if __name__ == "__main__":
    main()
