-- Images are now encrypted by the backend before upload (AES-256-GCM, FieldCipher, bound to
-- "analysis_images.content" and the image id) and stored at images/<image id>, with no case id
-- in the path. The GCM tag replaces the plaintext SHA-256 as the integrity check, so sha256 is
-- only kept for images uploaded before this change, until they are migrated (Phase 1d).

ALTER TABLE analysis_images ADD COLUMN encrypted BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE analysis_images ALTER COLUMN sha256 DROP NOT NULL;
