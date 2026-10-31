-- 01_metadata.sql - the protocol stored as data (11 tables)
-- A protocol modification adds ROWS here; no table ever changes shape.
BEGIN;

CREATE TABLE study (
    study_id     serial PRIMARY KEY,
    study_code   text NOT NULL UNIQUE,              -- e.g. DEMO-APT
    title        text NOT NULL
);

-- Each approved protocol version and the date it takes effect
CREATE TABLE protocol_version (
    protocol_version_id serial PRIMARY KEY,
    study_id            int  NOT NULL REFERENCES study,
    version_no          int  NOT NULL,
    effective_date      date NOT NULL,
    description         text,
    UNIQUE (study_id, version_no)
);

-- Treatment arms (A usual care, B, C ...)
CREATE TABLE arm (
    arm_id    serial PRIMARY KEY,
    study_id  int  NOT NULL REFERENCES study,
    arm_code  text NOT NULL,
    name      text NOT NULL,
    UNIQUE (study_id, arm_code)
);

-- Which arms are open under each protocol version, and their allocation weight
CREATE TABLE arm_period (
    arm_period_id       serial PRIMARY KEY,
    arm_id              int  NOT NULL REFERENCES arm,
    protocol_version_id int  NOT NULL REFERENCES protocol_version,
    allocation_weight   int  NOT NULL CHECK (allocation_weight > 0),
    open_from           date NOT NULL,
    closed_on           date,                        -- NULL = still open
    CHECK (closed_on IS NULL OR closed_on > open_from),
    UNIQUE (arm_id, protocol_version_id)
);

-- Scheduled visits (Baseline, Day 7, Day 28)
CREATE TABLE visit_def (
    visit_def_id  serial PRIMARY KEY,
    study_id      int  NOT NULL REFERENCES study,
    visit_code    text NOT NULL,
    name          text NOT NULL,
    day_offset    int  NOT NULL,                     -- days after randomisation
    UNIQUE (study_id, visit_code)
);

-- A form (CRF) and the visit it belongs to
CREATE TABLE form_def (
    form_def_id   serial PRIMARY KEY,
    study_id      int  NOT NULL REFERENCES study,
    visit_def_id  int  NOT NULL REFERENCES visit_def,
    form_code     text NOT NULL,
    name          text NOT NULL,
    UNIQUE (study_id, form_code)
);

-- A version of a form, introduced by a protocol version
CREATE TABLE form_version (
    form_version_id     serial PRIMARY KEY,
    form_def_id         int  NOT NULL REFERENCES form_def,
    protocol_version_id int  NOT NULL REFERENCES protocol_version,
    version_label       text NOT NULL,               -- e.g. day7 v1.0
    UNIQUE (form_def_id, protocol_version_id)
);

-- A question, defined once for the whole study
CREATE TABLE item_def (
    item_def_id  serial PRIMARY KEY,
    study_id     int  NOT NULL REFERENCES study,
    item_code    text NOT NULL,                      -- e.g. sbp
    label        text NOT NULL,
    data_type    text NOT NULL CHECK (data_type IN ('int','real','text','date','code')),
    UNIQUE (study_id, item_code)
);

-- Lists of allowed answers (e.g. 1=Male, 2=Female)
CREATE TABLE codelist (
    codelist_id    serial PRIMARY KEY,
    study_id       int  NOT NULL REFERENCES study,
    codelist_code  text NOT NULL,
    UNIQUE (study_id, codelist_code)
);

CREATE TABLE codelist_item (
    codelist_item_id  serial PRIMARY KEY,
    codelist_id       int  NOT NULL REFERENCES codelist,
    code_value        text NOT NULL,
    decode            text NOT NULL,
    sort_order        int  NOT NULL,
    UNIQUE (codelist_id, code_value)
);

-- A question as it appears on one form version: unit, valid range, required
CREATE TABLE item_version (
    item_version_id  serial PRIMARY KEY,
    item_def_id      int  NOT NULL REFERENCES item_def,
    form_version_id  int  NOT NULL REFERENCES form_version,
    item_order       int  NOT NULL,
    unit             text,
    range_min        numeric,
    range_max        numeric,
    required         boolean NOT NULL DEFAULT false,
    codelist_id      int  REFERENCES codelist,
    CHECK (range_min IS NULL OR range_max IS NULL OR range_min <= range_max),
    UNIQUE (form_version_id, item_def_id)
);

-- Indexes on foreign-key columns (PostgreSQL does not create these automatically)
CREATE INDEX ON protocol_version (study_id);
CREATE INDEX ON arm (study_id);
CREATE INDEX ON arm_period (arm_id);
CREATE INDEX ON arm_period (protocol_version_id);
CREATE INDEX ON visit_def (study_id);
CREATE INDEX ON form_def (study_id);
CREATE INDEX ON form_def (visit_def_id);
CREATE INDEX ON form_version (form_def_id);
CREATE INDEX ON form_version (protocol_version_id);
CREATE INDEX ON item_def (study_id);
CREATE INDEX ON codelist (study_id);
CREATE INDEX ON codelist_item (codelist_id);
CREATE INDEX ON item_version (item_def_id);
CREATE INDEX ON item_version (form_version_id);
CREATE INDEX ON item_version (codelist_id);

COMMIT;
