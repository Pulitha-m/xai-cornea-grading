-- As for the other tables: deny all access through Supabase's Data API roles;
-- the backend's table-owner connection is unaffected, so access control is enforced in the backend.
ALTER TABLE run_artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE case_signoffs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
