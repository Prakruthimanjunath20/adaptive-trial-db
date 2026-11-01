-- 03_audit.sql - audit trail (GCP: every change is attributable, dated, explained, and the original is kept)
BEGIN;

CREATE TABLE audit_log (
    audit_id    bigserial PRIMARY KEY,
    table_name  text        NOT NULL,
    row_pk      text        NOT NULL,                 -- primary key of the changed row
    action      text        NOT NULL CHECK (action IN ('INSERT','UPDATE','DELETE')),
    old_row     jsonb,                                -- the row before the change (NULL for INSERT)
    new_row     jsonb,                                -- the row after the change (NULL for DELETE)
    changed_by  text        NOT NULL DEFAULT current_user,
    changed_at  timestamptz NOT NULL DEFAULT now(),
    reason      text                                  -- required for UPDATE and DELETE
);
CREATE INDEX ON audit_log (table_name, row_pk);

-- One trigger function for any table; the primary-key column name is passed as an argument
CREATE FUNCTION audit_row_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    reason text := nullif(current_setting('app.change_reason', true), '');
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') AND reason IS NULL THEN
        RAISE EXCEPTION 'Reason for change required: run SET LOCAL app.change_reason = ''...'' first';
    END IF;
    INSERT INTO audit_log (table_name, row_pk, action, old_row, new_row, reason)
    VALUES (TG_TABLE_NAME,
            CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) ->> TG_ARGV[0] ELSE to_jsonb(NEW) ->> TG_ARGV[0] END,
            TG_OP,
            CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE to_jsonb(OLD) END,
            CASE WHEN TG_OP = 'DELETE' THEN NULL ELSE to_jsonb(NEW) END,
            reason);
    RETURN NULL;
END $$;

CREATE TRIGGER item_data_audit AFTER INSERT OR UPDATE OR DELETE ON item_data
    FOR EACH ROW EXECUTE FUNCTION audit_row_change('item_data_id');
CREATE TRIGGER randomisation_audit AFTER INSERT OR UPDATE OR DELETE ON randomisation
    FOR EACH ROW EXECUTE FUNCTION audit_row_change('randomisation_id');

-- The audit log is append-only: history cannot be edited or deleted
CREATE FUNCTION audit_log_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only: history cannot be changed';
END $$;
CREATE TRIGGER audit_log_no_change BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_append_only();

COMMIT;
