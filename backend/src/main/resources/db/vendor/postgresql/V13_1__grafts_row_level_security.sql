-- As for the other tables: deny all access through Supabase's Data API roles;
-- the backend's table-owner connection is unaffected, so access control is enforced in the backend.
ALTER TABLE grafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE graft_visits ENABLE ROW LEVEL SECURITY;
ALTER TABLE recommendation_runs ENABLE ROW LEVEL SECURITY;
-- Visits are at 3, 6 and 12 months (also checked by the backend; kept PostgreSQL-only, as H2 mis-evaluates it).
ALTER TABLE graft_visits ADD CONSTRAINT ck_graft_visits_month CHECK (visit_month IN (3, 6, 12));
