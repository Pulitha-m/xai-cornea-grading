-- Supabase exposes the public schema through its Data API (PostgREST).
-- Enabling RLS without policies denies all access via the anon/authenticated
-- API roles, while the backend's table-owner connection is unaffected.
ALTER TABLE roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY;
