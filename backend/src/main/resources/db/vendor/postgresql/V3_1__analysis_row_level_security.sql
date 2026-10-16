-- As for the auth tables: deny all access through Supabase's Data API roles;
-- the backend's table-owner connection is unaffected.
ALTER TABLE analysis_images ENABLE ROW LEVEL SECURITY;
ALTER TABLE analysis_runs ENABLE ROW LEVEL SECURITY;
