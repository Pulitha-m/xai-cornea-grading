-- v2 disease detection + severity runs (POST /api/analysis/disease), on images uploaded
-- through POST /api/analysis/images. Kept apart from analysis_runs (grading). Every
-- attempt is recorded, including rejections; Grad-CAM images are not stored.

CREATE TABLE disease_analysis_runs (
    id                 UUID                     PRIMARY KEY,
    image_id           UUID                     NOT NULL,
    case_id            VARCHAR(100)             NOT NULL,
    requested_by       BIGINT                   NOT NULL,
    status             VARCHAR(20)              NOT NULL,
    error_code         VARCHAR(50),
    forced             BOOLEAN                  NOT NULL,
    measurements_json  TEXT,
    result_json        TEXT,
    created_at         TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_disease_runs_image FOREIGN KEY (image_id) REFERENCES analysis_images (id),
    CONSTRAINT fk_disease_runs_user FOREIGN KEY (requested_by) REFERENCES app_users (id)
);

CREATE INDEX idx_disease_runs_image_id ON disease_analysis_runs (image_id);
CREATE INDEX idx_disease_runs_case_id ON disease_analysis_runs (case_id);
