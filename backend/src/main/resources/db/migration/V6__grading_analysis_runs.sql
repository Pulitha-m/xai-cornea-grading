-- Donor cornea grading runs (POST /api/analysis/grading), on images uploaded through
-- POST /api/analysis/images. Kept apart from analysis_runs (the combined workspace) and
-- disease_analysis_runs. Every attempt is recorded, including rejections.

CREATE TABLE grading_analysis_runs (
    id                      UUID                     PRIMARY KEY,
    image_id                UUID                     NOT NULL,
    case_id                 VARCHAR(100)             NOT NULL,
    requested_by            BIGINT                   NOT NULL,
    status                  VARCHAR(20)              NOT NULL,
    error_code              VARCHAR(50),
    ecd                     DOUBLE PRECISION,
    grade                   VARCHAR(10),
    clinical_features_json  TEXT,
    result_json             TEXT,
    created_at              TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_grading_runs_image FOREIGN KEY (image_id) REFERENCES analysis_images (id),
    CONSTRAINT fk_grading_runs_user FOREIGN KEY (requested_by) REFERENCES app_users (id)
);

CREATE INDEX idx_grading_runs_image_id ON grading_analysis_runs (image_id);
CREATE INDEX idx_grading_runs_case_id ON grading_analysis_runs (case_id);
