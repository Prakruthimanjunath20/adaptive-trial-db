-- Day 2 SQL warm-up: 

-- (a) Participants with no Day 7 visit
SELECT p.participant_id
FROM participant p
LEFT JOIN visit_instance vi
       ON vi.participant_id = p.participant_id
      AND vi.visit_def_id = (SELECT visit_def_id FROM visit_def WHERE visit_code = 'DAY7')
WHERE vi.visit_instance_id IS NULL
ORDER BY p.participant_id;

-- (b) Baseline form pivoted: one row per participant, one column per question
SELECT vi.participant_id,
       MAX(CASE WHEN idf.item_code = 'sex'        THEN d.value_text END) AS sex,
       MAX(CASE WHEN idf.item_code = 'weight_kg'  THEN d.value_num  END) AS weight_kg,
       MAX(CASE WHEN idf.item_code = 'sbp'        THEN d.value_num  END) AS sbp,
       MAX(CASE WHEN idf.item_code = 'heart_rate' THEN d.value_num  END) AS heart_rate
FROM item_data d
JOIN form_instance fi  ON fi.form_instance_id  = d.form_instance_id
JOIN visit_instance vi ON vi.visit_instance_id = fi.visit_instance_id
JOIN form_version fv   ON fv.form_version_id   = fi.form_version_id
JOIN form_def fd       ON fd.form_def_id       = fv.form_def_id
JOIN item_version iv   ON iv.item_version_id   = d.item_version_id
JOIN item_def idf      ON idf.item_def_id      = iv.item_def_id
WHERE fd.form_code = 'baseline'
GROUP BY vi.participant_id
ORDER BY vi.participant_id
LIMIT 5;

-- (c) Each participant's most recent SBP, using ROW_NUMBER()
WITH sbp AS (
    SELECT vi.participant_id, vd.visit_code, vi.visit_date, d.value_num AS sbp,
           ROW_NUMBER() OVER (PARTITION BY vi.participant_id
                              ORDER BY vi.visit_date DESC) AS rn
    FROM item_data d
    JOIN item_version iv   ON iv.item_version_id   = d.item_version_id
    JOIN item_def idf      ON idf.item_def_id      = iv.item_def_id
    JOIN form_instance fi  ON fi.form_instance_id  = d.form_instance_id
    JOIN visit_instance vi ON vi.visit_instance_id = fi.visit_instance_id
    JOIN visit_def vd      ON vd.visit_def_id      = vi.visit_def_id
    WHERE idf.item_code = 'sbp'
      AND d.value_num IS NOT NULL
)
SELECT participant_id, visit_code, visit_date, sbp
FROM sbp
WHERE rn = 1
ORDER BY participant_id
LIMIT 5;

-- (d) Numbers outside their question's range
SELECT vi.participant_id, vd.visit_code, idf.item_code,
       d.value_num, iv.range_min, iv.range_max
FROM item_data d
JOIN item_version iv   ON iv.item_version_id   = d.item_version_id
JOIN item_def idf      ON idf.item_def_id      = iv.item_def_id
JOIN form_instance fi  ON fi.form_instance_id  = d.form_instance_id
JOIN visit_instance vi ON vi.visit_instance_id = fi.visit_instance_id
JOIN visit_def vd      ON vd.visit_def_id      = vi.visit_def_id
WHERE d.value_num < iv.range_min
   OR d.value_num > iv.range_max
ORDER BY vi.participant_id;