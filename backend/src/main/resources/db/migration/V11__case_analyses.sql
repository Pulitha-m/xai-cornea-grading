-- One analysis request on a donor case: the chosen modules run on one of the case's images, with
-- their inputs taken from the case details. Each module still records its own run (linked here by
-- case_analysis_id); consistency_json holds the cross-module flags shown to the reviewer.

CREATE TABLE case_analyses (
    id                UUID                     PRIMARY KEY,
    donor_case_id     UUID                     NOT NULL,
    image_id          UUID                     NOT NULL,
    requested_by      BIGINT                   NOT NULL,
    modules           VARCHAR(100)             NOT NULL,
    consistency_json  TEXT,
    created_at        TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_case_analyses_case FOREIGN KEY (donor_case_id) REFERENCES donor_cases (id),
    CONSTRAINT fk_case_analyses_image FOREIGN KEY (image_id) REFERENCES analysis_images (id),
    CONSTRAINT fk_case_analyses_user FOREIGN KEY (requested_by) REFERENCES app_users (id)
);

CREATE INDEX idx_case_analyses_donor_case_id ON case_analyses (donor_case_id);

ALTER TABLE cellular_analysis_runs ADD COLUMN case_analysis_id UUID;
ALTER TABLE cellular_analysis_runs
    ADD CONSTRAINT fk_cellular_runs_case_analysis FOREIGN KEY (case_analysis_id) REFERENCES case_analyses (id);
CREATE INDEX idx_cellular_runs_case_analysis_id ON cellular_analysis_runs (case_analysis_id);

ALTER TABLE grading_analysis_runs ADD COLUMN case_analysis_id UUID;
ALTER TABLE grading_analysis_runs
    ADD CONSTRAINT fk_grading_runs_case_analysis FOREIGN KEY (case_analysis_id) REFERENCES case_analyses (id);
CREATE INDEX idx_grading_runs_case_analysis_id ON grading_analysis_runs (case_analysis_id);

ALTER TABLE disease_analysis_runs ADD COLUMN case_analysis_id UUID;
ALTER TABLE disease_analysis_runs
    ADD CONSTRAINT fk_disease_runs_case_analysis FOREIGN KEY (case_analysis_id) REFERENCES case_analyses (id);
CREATE INDEX idx_disease_runs_case_analysis_id ON disease_analysis_runs (case_analysis_id);
