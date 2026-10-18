-- The 24 clinical features submitted with each analysis (JSON object, as sent to ml-service).
ALTER TABLE analysis_runs ADD COLUMN clinical_features_json TEXT;
