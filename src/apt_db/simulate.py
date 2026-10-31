"""Simulate synthetic participants and their form data (no real patient data).

Usage:  python -m apt_db.simulate --n 150 --start 2026-01-05 --end 2026-03-31 --seed 2026

Everything is driven by the metadata already in the database:
  - the protocol version in force on each randomisation date,
  - the arms open on that date and their allocation weights (permuted blocks),
  - the latest form version in force on each visit date and its items.
A few out-of-range values are planted on purpose so that edit checks have something to find.
"""
import argparse
import random
from datetime import date, timedelta

from apt_db.db import connect

SITES = {"S01": "Site 01 (fictional)", "S02": "Site 02 (fictional)", "S03": "Site 03 (fictional)"}
MISSING_RATE = 0.04  # share of non-required answers left empty


def version_in_force(versions, day):
    """The latest protocol version whose effective date is on or before `day`."""
    return max((v for v in versions if v["effective_date"] <= day), key=lambda v: v["version_no"])


def open_arms(conn, day):
    """Arms open on `day`, with their allocation weights."""
    return conn.execute(
        """SELECT a.arm_id, a.arm_code, ap.allocation_weight
           FROM arm_period ap JOIN arm a USING (arm_id)
           WHERE ap.open_from <= %s AND (ap.closed_on IS NULL OR %s < ap.closed_on)
           ORDER BY a.arm_code""",
        (day, day),
    ).fetchall()


def form_items(conn, form_code, version_no):
    """The latest version of a form introduced on or before protocol `version_no`, with its items."""
    rows = conn.execute(
        """SELECT fv.form_version_id, iv.item_version_id, idf.item_code, idf.data_type,
                  iv.range_min, iv.range_max, iv.required
           FROM form_version fv
           JOIN form_def fd USING (form_def_id)
           JOIN protocol_version pv USING (protocol_version_id)
           JOIN item_version iv USING (form_version_id)
           JOIN item_def idf USING (item_def_id)
           WHERE fd.form_code = %s
             AND pv.version_no = (SELECT max(pv2.version_no)
                                  FROM form_version fv2
                                  JOIN form_def fd2 USING (form_def_id)
                                  JOIN protocol_version pv2 USING (protocol_version_id)
                                  WHERE fd2.form_code = %s AND pv2.version_no <= %s)
           ORDER BY iv.item_order""",
        (form_code, form_code, version_no),
    ).fetchall()
    return rows[0][0], rows


def make_value(rng, item_code, person):
    """A realistic synthetic value for one item."""
    r = rng
    values = {
        "age": lambda: min(95, max(18, round(r.gauss(62, 14)))),
        "spo2": lambda: r.randint(80, 93) if person["visit"] == "BASELINE" else r.randint(88, 99),
        "fio2": lambda: r.choice([0.28, 0.35, 0.40, 0.50, 0.60]),
        "consent_date": lambda: person["consent_date"],
        "sex": lambda: "1" if r.random() < 0.55 else "2",
        "weight_kg": lambda: round(min(160, max(40, r.gauss(80, 15))), 1),
        "sbp": lambda: round(r.gauss(125 if person["visit"] == "BASELINE" else 122, 15)),
        "dbp": lambda: round(r.gauss(75, 10)),
        "heart_rate": lambda: round(r.gauss(90, 15)),
        "creatinine_umol_l": lambda: round(r.lognormvariate(4.45, 0.35), 1),
        "ventilated": lambda: "1" if r.random() < 0.15 else "0",
        "crp_mg_l": lambda: round(r.lognormvariate(4.2, 0.6), 1),
        "day28_status": lambda: "2" if person["died_on"] else "1",
        "discharge_date": lambda: None if person["died_on"]
                                  else person["randomised"] + timedelta(days=r.randint(3, 27)),
    }
    return values[item_code]()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--start", type=date.fromisoformat, default=date(2026, 1, 5))
    ap.add_argument("--end", type=date.fromisoformat, default=date(2026, 3, 31))
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()
    rng = random.Random(args.seed)  # fixed seed = same data every run

    with connect() as conn:  # one transaction
        study_id = conn.execute("SELECT study_id FROM study WHERE study_code = 'DEMO-APT'").fetchone()[0]
        for code, name in SITES.items():
            conn.execute(
                "INSERT INTO site (study_id, site_code, name) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (study_id, code, name),
            )
        site_ids = dict(conn.execute("SELECT site_code, site_id FROM site").fetchall())
        versions = [dict(protocol_version_id=a, version_no=b, effective_date=c) for a, b, c in
                    conn.execute("SELECT protocol_version_id, version_no, effective_date FROM protocol_version")]
        visits = conn.execute(
            """SELECT vd.visit_code, vd.visit_def_id, vd.day_offset, array_agg(fd.form_code ORDER BY fd.form_def_id)
               FROM visit_def vd JOIN form_def fd USING (visit_def_id)
               GROUP BY 1, 2, 3 ORDER BY vd.day_offset"""
        ).fetchall()

        # Next participant number at each site (continues numbering on later runs)
        next_no = {code: 1 for code in SITES}
        for code, max_no in conn.execute(
            """SELECT s.site_code, max(split_part(p.participant_id, '-', 2)::int)
               FROM participant p JOIN site s USING (site_id) GROUP BY 1"""
        ):
            next_no[code] = max_no + 1

        span = (args.end - args.start).days
        rand_dates = sorted(args.start + timedelta(days=rng.randint(0, span)) for _ in range(args.n))
        planted = {17: ("BASELINE", "sbp", lambda v: v * 10),        # typo: 1250 instead of 125
                   42: ("BASELINE", "weight_kg", lambda v: round(v / 10, 1)),  # decimal slip
                   88: ("DAY7", "spo2", lambda v: v // 10)}          # dropped digit

        block, block_key, item_rows = [], None, 0
        for seq, rand_day in enumerate(rand_dates):
            site = rng.choice(list(SITES))
            pid = f"{site}-{next_no[site]:04d}"
            next_no[site] += 1
            pv = version_in_force(versions, rand_day)

            # Permuted-block randomisation over the arms open today (new block if the arms change)
            arms = open_arms(conn, rand_day)
            key = tuple(arms)
            if key != block_key or not block:
                block = [arm_id for arm_id, _, w in arms for _ in range(2 * w)]
                rng.shuffle(block)
                block_key = key
            arm_id = block.pop()

            r = rng.random()
            died_on = (rand_day + timedelta(days=rng.randint(2, 6)) if r < 0.05 else
                       rand_day + timedelta(days=rng.randint(8, 27)) if r < 0.15 else None)
            person = dict(randomised=rand_day, consent_date=rand_day - timedelta(days=rng.choice([0, 0, 1])),
                          died_on=died_on, visit=None)

            conn.execute("INSERT INTO participant (participant_id, site_id, consent_date) VALUES (%s, %s, %s)",
                         (pid, site_ids[site], person["consent_date"]))
            conn.execute(
                """INSERT INTO randomisation (participant_id, arm_id, protocol_version_id, randomised_at)
                   VALUES (%s, %s, %s, %s)""",
                (pid, arm_id, pv["protocol_version_id"], rand_day),
            )

            for visit_code, visit_def_id, day_offset, form_codes in visits:
                visit_day = rand_day + timedelta(days=day_offset)
                if died_on and visit_code != "DAY28" and visit_day >= died_on:
                    continue  # no visit after death (the Day 28 outcome is still recorded)
                person["visit"] = visit_code
                vi_id = conn.execute(
                    """INSERT INTO visit_instance (participant_id, visit_def_id, visit_date)
                       VALUES (%s, %s, %s) RETURNING visit_instance_id""",
                    (pid, visit_def_id, visit_day),
                ).fetchone()[0]
                version_no = version_in_force(versions, visit_day)["version_no"]
                for form_code in form_codes:
                    fv_id, items = form_items(conn, form_code, version_no)
                    fi_id = conn.execute(
                        """INSERT INTO form_instance (visit_instance_id, form_version_id, status)
                           VALUES (%s, %s, 'complete') RETURNING form_instance_id""",
                        (vi_id, fv_id),
                    ).fetchone()[0]
                    for _, iv_id, item_code, data_type, *_rest, required in items:
                        if not required and rng.random() < MISSING_RATE:
                            continue
                        value = make_value(rng, item_code, person)
                        if value is None:
                            continue
                        if seq in planted and planted[seq][:2] == (visit_code, item_code):
                            value = planted[seq][2](value)
                        num = value if data_type in ("int", "real") else None
                        txt = value if data_type in ("code", "text") else None
                        dte = value if data_type == "date" else None
                        conn.execute(
                            """INSERT INTO item_data (form_instance_id, item_version_id, value_num, value_text, value_date)
                               VALUES (%s, %s, %s, %s, %s)""",
                            (fi_id, iv_id, num, txt, dte),
                        )
                        item_rows += 1

        print(f"Simulated {args.n} participants randomised {args.start} to {args.end} "
              f"(seed {args.seed}): {item_rows} answers saved.")


if __name__ == "__main__":
    main()