-- Cellular analysis runs (POST /api/analysis/cellular), on images uploaded through
-- POST /api/analysis/images. Kept apart from the other modules' runs. Every attempt is recorded,
-- including rejections; the overlay images are not stored.

CREATE TABLE cellular_analysis_runs (
    id            UUID                     PRIMARY KEY,
    image_id      UUID                     NOT NULL,
    case_id       VARCHAR(100)             NOT NULL,
    requested_by  BIGINT                   NOT NULL,
    status        VARCHAR(20)              NOT NULL,
    error_code    VARCHAR(50),
    cell_count    INTEGER,
    ecd           DOUBLE PRECISION,
    cv            DOUBLE PRECISION,
    hex           DOUBLE PRECISION,
    reliable      BOOLEAN,
    result_json   TEXT,
    created_at    TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_cellular_runs_image FOREIGN KEY (image_id) REFERENCES analysis_images (id),
    CONSTRAINT fk_cellular_runs_user FOREIGN KEY (requested_by) REFERENCES app_users (id)
);

CREATE INDEX idx_cellular_runs_image_id ON cellular_analysis_runs (image_id);
CREATE INDEX idx_cellular_runs_case_id ON cellular_analysis_runs (case_id);
