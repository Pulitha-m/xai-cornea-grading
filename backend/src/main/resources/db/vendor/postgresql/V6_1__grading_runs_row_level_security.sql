-- As for the other tables: deny all access through Supabase's Data API roles;
-- the backend's table-owner connection is unaffected.
ALTER TABLE grading_analysis_runs ENABLE ROW LEVEL SECURITY;
