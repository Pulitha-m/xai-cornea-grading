-- Recommendation runs (POST /api/analysis/recommendation/match and /followup): donor-tissue
-- ranking for a recipient request, and the post-transplant follow-up recommendation at the
-- 12-month visit. No images are involved. Kept apart from the other modules' runs. Every
-- attempt is recorded, including rejections.

CREATE TABLE recommendation_runs (
    id                 UUID                     PRIMARY KEY,
    kind               VARCHAR(20)              NOT NULL,
    subject_id         VARCHAR(100)             NOT NULL,
    requested_by       BIGINT                   NOT NULL,
    status             VARCHAR(20)              NOT NULL,
    error_code         VARCHAR(50),
    method_used        VARCHAR(50),
    top_record_id      VARCHAR(100),
    alert              VARCHAR(10),
    next_visit_months  INTEGER,
    result_json        TEXT,
    created_at         TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_recommendation_runs_user FOREIGN KEY (requested_by) REFERENCES app_users (id)
);

CREATE INDEX idx_recommendation_runs_subject_id ON recommendation_runs (subject_id);
CREATE INDEX idx_recommendation_runs_kind ON recommendation_runs (kind);
