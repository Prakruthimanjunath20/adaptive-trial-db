-- 04_datacut.sql - frozen, reproducible interim data cuts (e.g. IA1 for the DMC)
BEGIN;

CREATE TABLE data_cut (
    cut_id      serial PRIMARY KEY,
    cut_code    text        NOT NULL UNIQUE,          -- e.g. IA1
    cut_date    date        NOT NULL,                 -- data cut-off date
    created_by  text        NOT NULL DEFAULT current_user,
    created_at  timestamptz NOT NULL DEFAULT now(),
    row_count   int,
    sha256      text                                  -- fingerprint of the exported CSV
);

-- A frozen copy of every answer in the cut. Later corrections to live data do not touch it.
CREATE TABLE data_cut_item (
    cut_id            int  NOT NULL REFERENCES data_cut,
    participant_id    text NOT NULL,
    site_code         text NOT NULL,
    arm_code          text NOT NULL,
    protocol_version  int  NOT NULL,
    randomised_at     date NOT NULL,
    visit_code        text NOT NULL,
    visit_date        date NOT NULL,
    form_version      text NOT NULL,
    item_code         text NOT NULL,
    value             text,
    PRIMARY KEY (cut_id, participant_id, visit_code, form_version, item_code)
);

COMMIT;
