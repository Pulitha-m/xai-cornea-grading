# Authentication & access control

## Flow

1. The SPA calls `GET /api/auth/csrf`, which sets a readable `XSRF-TOKEN` cookie.
2. `POST /api/auth/login` (`{identifier, password, rememberMe}`; header `X-XSRF-TOKEN`) returns
   a 15-minute JWT access token in the body and sets the `cornealai_refresh` cookie
   (HttpOnly, Secure, SameSite=Strict, `Path=/api/auth`).
3. The SPA keeps the access token **in memory only** and sends `Authorization: Bearer …`.
4. Before expiry, or after a 401, the SPA calls `POST /api/auth/refresh`. The refresh token is rotated
   on every use; replaying an already-rotated token revokes the whole session (theft detection).
5. `POST /api/auth/logout` revokes the session server-side and clears the cookie.
   On page reload the session is restored from the refresh cookie.

The backend re-loads the user and role from the database on every request, so role changes and
account disabling take effect immediately; JWT claims are never trusted for authorization.

## Endpoints

| Method | Path | Access |
| --- | --- | --- |
| GET | `/api/auth/csrf` | public |
| POST | `/api/auth/login`, `/api/auth/refresh`, `/api/auth/logout` | public + CSRF header |
| GET | `/api/auth/me` | authenticated |
| GET | `/api/users` | `users:read` |
| POST | `/api/users` | `users:manage` + `roles:assign` |
| PUT | `/api/users/{id}/role` | `roles:assign` (not on self) |
| PATCH | `/api/users/{id}/status` | `users:manage` (cannot disable self) |
| PUT | `/api/users/{id}/password` | `users:manage` (admin reset) |
| POST | `/api/analysis` | `analysis:run` |
| GET | `/actuator/health` | public |

## Roles

| Role | Permissions | Dashboard |
| --- | --- | --- |
| ADMIN | `users:read`, `users:manage`, `roles:assign` | `/admin/dashboard` |
| MANAGER | `users:read` | `/manager/dashboard` |
| DOCTOR | `analysis:run` | `/doctor/dashboard` |
| NURSE | `analysis:run` | `/nurse/dashboard` |
| SUPPORT_STAFF | — | `/support/dashboard` |

The mapping lives in `backend/.../user/entity/RoleName.java`. Accounts have exactly one role and
are created by administrators (no self-registration).

## Configuration

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `JWT_SECRET` | yes | — | Base64 HMAC key ≥ 256 bits (`openssl rand -base64 48`) |
| `JWT_ACCESS_TOKEN_TTL` | no | `15m` | Access-token lifetime |
| `REFRESH_TOKEN_REMEMBER_ME_TTL` | no | `7d` | Session lifetime with "keep me signed in" |
| `REFRESH_TOKEN_SESSION_TTL` | no | `12h` | Session lifetime otherwise (browser-session cookie) |
| `AUTH_COOKIE_SECURE` | no | `true` | Set `false` only for plain-HTTP testing on a non-localhost host |
| `CORS_ALLOWED_ORIGINS` | no | `http://localhost:3000` | Only needed for cross-origin API access |
| `BOOTSTRAP_ADMIN_EMAIL` / `_USERNAME` / `_PASSWORD` / `_FULL_NAME` | first run | — | Creates the first admin |

The frontend reaches the API through a same-origin `/api` proxy: nginx in Docker
(`frontend/nginx.conf`) and the Vite dev server locally (`VITE_DEV_API_TARGET`, default
`http://localhost:8080`). Keep it that way — the SameSite=Strict cookies depend on it.

## First administrator

1. Set `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_USERNAME` and a strong `BOOTSTRAP_ADMIN_PASSWORD`
   (12–72 characters) in `.env`.
2. Start the backend. If no ADMIN exists, the account is created with a BCrypt hash and a warning is logged.
3. **Remove `BOOTSTRAP_ADMIN_PASSWORD` from `.env`** and restart. The runner never runs again while an ADMIN exists.
4. Sign in and create the remaining accounts from the admin dashboard.

## Database

Flyway migration `V2__auth_schema.sql` creates `roles` (seeded), `app_users` and `refresh_tokens`.
On PostgreSQL, `db/vendor/postgresql/V2_1__auth_row_level_security.sql` enables RLS on these tables so
Supabase's public Data API cannot read them (the backend's owner connection is unaffected).
Migrations run automatically on backend start; nothing existing is altered or dropped.

## Not implemented yet

- Self-service password recovery (needs a verified email channel). The login page has a documented
  integration point; until then administrators reset passwords.
- Record-level authorization: the API has no stored patient/tissue records yet. Apply ownership or
  assignment checks when those endpoints are introduced.
- Rate limiting beyond per-account lockout (5 failures → 15 min), e.g. per-IP throttling at the proxy.
