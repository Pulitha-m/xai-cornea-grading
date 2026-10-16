# xai-cornea-grading

Corneal Cellular Intelligence Platform: React frontend, Spring Boot backend, FastAPI ML service, and the research code behind the grading model.

| Directory | Contents |
|---|---|
| `frontend/` | React + Vite app (served by nginx in Docker) |
| `backend/` | Spring Boot API: authentication, roles, image upload and analysis requests |
| `ml-service/` | FastAPI inference: image validation, corneal-image domain check, ECD grading (see `ml-service/README.md`) |
| `ml/grading/` | Research notebooks and scripts; findings in `FINDINGS.md`, `RESULTS.md`, `CLAIMS_AUDIT.md` |

## Running with Docker

1. Copy `.env.example` to `.env` and fill in the values. `.env` is git-ignored; never commit it.
2. **Image storage:**
   - In Supabase, create a Storage bucket named as in `SUPABASE_STORAGE_BUCKET` (default `specular-images`) and leave **"Public bucket" off**. The backend checks the bucket and refuses to use a public one.
   - Set `SUPABASE_URL` to the project URL.
   - Set `SUPABASE_SERVICE_ROLE_KEY` to the service-role key. It is used only by the backend and is never sent to the browser.
3. Run `docker compose up --build`. The frontend is on http://localhost:3000.

   The `ml-service` build downloads the pinned CPU build of PyTorch and the ResNet-18 weights to regenerate its ONNX backbone, and verifies it against the trained classifier. Build containers need internet access; on networks or VPNs that block Docker's DNS servers, see Docker Desktop's DNS settings.

Database migrations (Flyway) run when the backend starts. `V3__analysis_images.sql` adds the `analysis_images` and `analysis_runs` tables.

## What the analysis does and does not do

- **Images are checked before analysis:** JPEG or PNG only, plus size and dimension limits. A trained validator rejects images that are not specular microscopy images of the corneal endothelium. It is evaluated on held-out photos, documents and synthetic images, but **not clinically validated**, and it does not assess image quality (see `ml-service/README.md`).
- **The grade comes from ECD alone** (cut points 2232 / 2497 cells/mm²) and is decision support for a specialist. It is not an eye-bank grading decision.
- **Not implemented yet:** cellular analysis, disease screening and recommendation. They report `not_implemented` instead of values.
