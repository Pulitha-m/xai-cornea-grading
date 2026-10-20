-- Result images of a run (cellular overlays, Grad-CAM maps, grading image maps), stored encrypted in
-- the image bucket at artifacts/<id> (AES-256-GCM, bound to "run_artifacts.content" and the id).
-- json_path says where the image goes back into the run's stored result when it is shown again.
CREATE TABLE run_artifacts (
    id             UUID                     PRIMARY KEY,
    module         VARCHAR(20)              NOT NULL,
    run_id         UUID                     NOT NULL,
    donor_case_id  UUID                     NOT NULL,
    json_path      VARCHAR(200)             NOT NULL,
    content_type   VARCHAR(50)              NOT NULL,
    object_path    VARCHAR(300)             NOT NULL,
    size_bytes     BIGINT                   NOT NULL,
    created_at     TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_run_artifacts_case FOREIGN KEY (donor_case_id) REFERENCES donor_cases (id)
);

CREATE INDEX idx_run_artifacts_run ON run_artifacts (module, run_id);

-- Specialist sign-off of a case: what the specialist confirmed. Append-only; the newest is current.
-- notes_enc is free text and may identify someone, so it is encrypted.
CREATE TABLE case_signoffs (
    id                UUID                     PRIMARY KEY,
    donor_case_id     UUID                     NOT NULL,
    case_analysis_id  UUID,
    signed_by         BIGINT                   NOT NULL,
    confirmed_grade   VARCHAR(5)               NOT NULL,
    disease_finding   VARCHAR(20)              NOT NULL,
    ecd               DOUBLE PRECISION,
    cv                DOUBLE PRECISION,
    hex_percent       DOUBLE PRECISION,
    notes_enc         BYTEA,
    created_at        TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_case_signoffs_case FOREIGN KEY (donor_case_id) REFERENCES donor_cases (id),
    CONSTRAINT fk_case_signoffs_analysis FOREIGN KEY (case_analysis_id) REFERENCES case_analyses (id),
    CONSTRAINT fk_case_signoffs_user FOREIGN KEY (signed_by) REFERENCES app_users (id)
);

CREATE INDEX idx_case_signoffs_case ON case_signoffs (donor_case_id, created_at);

-- Who decrypted or changed what, and when. Append-only. Never holds the sensitive values themselves.
CREATE TABLE audit_events (
    id            UUID                     PRIMARY KEY,
    occurred_at   TIMESTAMP WITH TIME ZONE NOT NULL,
    user_id       BIGINT                   NOT NULL,
    action        VARCHAR(40)              NOT NULL,
    subject_type  VARCHAR(30),
    subject_id    UUID,
    detail        VARCHAR(200),
    CONSTRAINT fk_audit_events_user FOREIGN KEY (user_id) REFERENCES app_users (id)
);

CREATE INDEX idx_audit_events_occurred_at ON audit_events (occurred_at);
CREATE INDEX idx_audit_events_subject ON audit_events (subject_type, subject_id);
