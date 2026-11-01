"""Five tests that prove the main claims of this project. Run with:  pytest -q"""
from pathlib import Path

import psycopg
import pytest

from apt_db.datacut import sha256, verify
from apt_db.db import connect

ROOT = Path(__file__).resolve().parent.parent
COLUMNS_SQL = """SELECT table_name || '.' || column_name || ' ' || data_type
                 FROM information_schema.columns
                 WHERE table_schema = 'public' AND table_name = ANY(%s)
                 ORDER BY table_name, ordinal_position"""


@pytest.fixture
def conn():
    """A database connection; anything a test changes is rolled back afterwards."""
    with connect() as c:
        yield c
        c.rollback()


def test_1_modifications_did_not_change_any_table_structure(conn):
    before = (ROOT / "docs" / "schema_before.txt").read_text().split("\n")
    before = [line for line in before if line]
    tables = sorted({line.split(".")[0] for line in before})
    now = [row[0] for row in conn.execute(COLUMNS_SQL, (tables,))]
    assert len(tables) == 17
    assert now == before


def test_2_old_forms_stay_valid_and_crp_is_only_on_the_new_version(conn):
    # every answer belongs to a question that is on its own form version
    mismatched = conn.execute(
        """SELECT count(*) FROM item_data d
           JOIN item_version iv USING (item_version_id)
           JOIN form_instance fi USING (form_instance_id)
           WHERE iv.form_version_id <> fi.form_version_id"""
    ).fetchone()[0]
    assert mismatched == 0
    counts = dict(conn.execute(
        """SELECT fv.version_label, count(*) FROM form_instance fi
           JOIN form_version fv USING (form_version_id)
           WHERE fv.version_label LIKE 'day7%' GROUP BY 1"""
    ).fetchall())
    assert counts["day7 v1.0"] > 0 and counts["day7 v2.0"] > 0
    crp_on_v1 = conn.execute(
        "SELECT count(*) FROM v_day7_wide WHERE form_version = 'day7 v1.0' AND crp_mg_l IS NOT NULL"
    ).fetchone()[0]
    assert crp_on_v1 == 0


def test_3_every_randomisation_used_an_arm_open_that_day(conn):
    outside = conn.execute(
        """SELECT count(*) FROM randomisation r
           WHERE NOT EXISTS (SELECT 1 FROM arm_period ap
                             WHERE ap.arm_id = r.arm_id AND ap.open_from <= r.randomised_at
                               AND (ap.closed_on IS NULL OR r.randomised_at < ap.closed_on))"""
    ).fetchone()[0]
    arm_b_after_close = conn.execute(
        """SELECT count(*) FROM randomisation r JOIN arm a USING (arm_id)
           WHERE a.arm_code = 'B' AND r.randomised_at >= '2026-05-15'"""
    ).fetchone()[0]
    assert outside == 0
    assert arm_b_after_close == 0


def test_4_change_without_reason_is_refused_and_change_with_reason_is_audited(conn):
    item_data_id = conn.execute("SELECT min(item_data_id) FROM item_data WHERE value_num IS NOT NULL").fetchone()[0]
    with pytest.raises(psycopg.errors.RaiseException, match="Reason for change required"):
        with conn.transaction():
            conn.execute("UPDATE item_data SET value_num = value_num + 1 WHERE item_data_id = %s", (item_data_id,))

    last = conn.execute("SELECT coalesce(max(audit_id), 0) FROM audit_log").fetchone()[0]
    conn.execute("SELECT set_config('app.change_reason', 'pytest: audit check', true)")
    conn.execute("UPDATE item_data SET value_num = value_num + 1 WHERE item_data_id = %s", (item_data_id,))
    new_rows = conn.execute(
        "SELECT action, row_pk, reason FROM audit_log WHERE audit_id > %s", (last,)
    ).fetchall()
    assert new_rows == [("UPDATE", str(item_data_id), "pytest: audit check")]


def test_5_interim_cut_ia1_is_reproducible(conn):
    assert verify(conn, "IA1")
    stored = conn.execute("SELECT sha256 FROM data_cut WHERE cut_code = 'IA1'").fetchone()[0]
    csv_text = (ROOT / "data" / "cuts" / "IA1.csv").read_text(encoding="utf-8")
    assert sha256(csv_text) == stored