-- As for the other tables: deny all access through Supabase's Data API roles;
-- the backend's table-owner connection is unaffected, so access control is enforced in the backend.
ALTER TABLE donor_cases ENABLE ROW LEVEL SECURITY;
