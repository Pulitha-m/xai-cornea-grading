-- As for the other tables: deny all access through Supabase's Data API roles;
-- the backend's table-owner connection is unaffected.
ALTER TABLE cellular_analysis_runs ENABLE ROW LEVEL SECURITY;
