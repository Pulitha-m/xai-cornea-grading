-- As for the other tables: deny all access through Supabase's Data API roles;
-- the backend's table-owner connection is unaffected, so access control is enforced in the backend.
ALTER TABLE case_analyses ENABLE ROW LEVEL SECURITY;
