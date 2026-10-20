-- A transplanted cornea: a signed-off donor case allocated to a recipient request. One graft per
-- cornea, so an allocated cornea is no longer a matching candidate. request_id is the recipient
-- request's study code (e.g. Q0012), never a recipient name or hospital number.
CREATE TABLE grafts (
    id                UUID                     PRIMARY KEY,
    donor_case_id     UUID                     NOT NULL,
    request_id        VARCHAR(100)             NOT NULL,
    procedure_type    VARCHAR(10)              NOT NULL,
    indication        VARCHAR(60)              NOT NULL,
    surgery_date      DATE,
    rejection_by_12m  BOOLEAN,
    match_run_id      UUID,
    allocated_by      BIGINT                   NOT NULL,
    created_at        TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at        TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uk_grafts_case UNIQUE (donor_case_id),
    CONSTRAINT fk_grafts_case FOREIGN KEY (donor_case_id) REFERENCES donor_cases (id),
    CONSTRAINT fk_grafts_match_run FOREIGN KEY (match_run_id) REFERENCES recommendation_runs (id),
    CONSTRAINT fk_grafts_user FOREIGN KEY (allocated_by) REFERENCES app_users (id)
);

CREATE INDEX idx_grafts_request_id ON grafts (request_id);

-- Specular microscopy of the graft at the 3-, 6- and 12-month follow-up visits (one row per visit).
CREATE TABLE graft_visits (
    id           UUID                     PRIMARY KEY,
    graft_id     UUID                     NOT NULL,
    visit_month  INTEGER                  NOT NULL,
    ecd          DOUBLE PRECISION         NOT NULL,
    cv           DOUBLE PRECISION         NOT NULL,
    hex          DOUBLE PRECISION         NOT NULL,
    visit_date   DATE,
    recorded_by  BIGINT                   NOT NULL,
    updated_at   TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uk_graft_visits_month UNIQUE (graft_id, visit_month),
    CONSTRAINT fk_graft_visits_graft FOREIGN KEY (graft_id) REFERENCES grafts (id),
    CONSTRAINT fk_graft_visits_user FOREIGN KEY (recorded_by) REFERENCES app_users (id)
);

-- The inputs each recommendation run was given, so a saved report can be shown again in full.
ALTER TABLE recommendation_runs ADD COLUMN inputs_json TEXT;
