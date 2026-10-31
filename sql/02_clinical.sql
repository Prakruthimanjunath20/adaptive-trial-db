-- 02_clinical.sql - the patient data (6 tables)
-- Values are stored one per row ("long" format), each linked to the item version that collected it.
BEGIN;

CREATE TABLE site (
    site_id    serial PRIMARY KEY,
    study_id   int  NOT NULL REFERENCES study,
    site_code  text NOT NULL,                        -- e.g. S01
    name       text NOT NULL,
    UNIQUE (study_id, site_code)
);

CREATE TABLE participant (
    participant_id  text PRIMARY KEY CHECK (participant_id ~ '^S[0-9]{2}-[0-9]{4}$'),  -- e.g. S01-0001
    site_id         int  NOT NULL REFERENCES site,
    consent_date    date NOT NULL
);

-- One randomisation per participant, recording the arm and the protocol version in force
CREATE TABLE randomisation (
    randomisation_id     serial PRIMARY KEY,
    participant_id       text NOT NULL UNIQUE REFERENCES participant,
    arm_id               int  NOT NULL REFERENCES arm,
    protocol_version_id  int  NOT NULL REFERENCES protocol_version,
    randomised_at        date NOT NULL
);

CREATE TABLE visit_instance (
    visit_instance_id  serial PRIMARY KEY,
    participant_id     text NOT NULL REFERENCES participant,
    visit_def_id       int  NOT NULL REFERENCES visit_def,
    visit_date         date NOT NULL,
    UNIQUE (participant_id, visit_def_id)
);

CREATE TABLE form_instance (
    form_instance_id   serial PRIMARY KEY,
    visit_instance_id  int  NOT NULL REFERENCES visit_instance,
    form_version_id    int  NOT NULL REFERENCES form_version,
    status             text NOT NULL DEFAULT 'not_started'
                       CHECK (status IN ('not_started','in_progress','complete','locked')),
    UNIQUE (visit_instance_id, form_version_id)
);

-- One row per answer. Exactly one typed value column is used (or none if missing).
CREATE TABLE item_data (
    item_data_id      bigserial PRIMARY KEY,
    form_instance_id  int  NOT NULL REFERENCES form_instance,
    item_version_id   int  NOT NULL REFERENCES item_version,
    value_num         numeric,
    value_text        text,
    value_date        date,
    CHECK (num_nonnulls(value_num, value_text, value_date) <= 1),
    UNIQUE (form_instance_id, item_version_id)
);

-- Indexes on foreign-key columns
CREATE INDEX ON site (study_id);
CREATE INDEX ON participant (site_id);
CREATE INDEX ON randomisation (arm_id);
CREATE INDEX ON randomisation (protocol_version_id);
CREATE INDEX ON visit_instance (visit_def_id);
CREATE INDEX ON form_instance (form_version_id);
CREATE INDEX ON item_data (item_version_id);

COMMIT;
