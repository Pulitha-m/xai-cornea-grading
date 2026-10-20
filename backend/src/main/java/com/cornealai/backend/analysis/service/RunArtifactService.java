package com.cornealai.backend.analysis.service;

import com.cornealai.backend.analysis.entity.RunArtifact;
import com.cornealai.backend.analysis.repository.RunArtifactRepository;
import com.cornealai.backend.analysis.storage.ImageStorage;
import com.cornealai.backend.common.crypto.FieldCipher;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

import java.util.Base64;
import java.util.List;
import java.util.UUID;

/**
 * Keeps the result images of a run (cellular overlays, Grad-CAM maps, grading image maps), which are
 * left out of the stored result JSON: each is encrypted (bound to {@link #CONTENT_FIELD} and its id) and
 * stored at artifacts/&lt;id&gt;. When a run is shown again, {@link #restore} puts them back into its result.
 * Images are supplementary: if one cannot be stored, the run is still saved and the failure is logged.
 */
@Service
public class RunArtifactService {

    public static final String CONTENT_FIELD = "run_artifacts.content";
    private static final Logger log = LoggerFactory.getLogger(RunArtifactService.class);

    private final RunArtifactRepository artifacts;
    private final ImageStorage storage;
    private final FieldCipher cipher;

    public RunArtifactService(RunArtifactRepository artifacts, ImageStorage storage, FieldCipher cipher) {
        this.artifacts = artifacts;
        this.storage = storage;
        this.cipher = cipher;
    }

    /** A base64 image from a module response and where it belongs in the result (JSON Pointer). */
    public record Image(String jsonPath, String base64) {
    }

    public void store(String module, UUID runId, UUID donorCaseId, List<Image> images) {
        for (Image image : images) {
            if (image.base64() == null || image.base64().isBlank()) {
                continue;
            }
            UUID id = UUID.randomUUID();
            String objectPath = "artifacts/" + id;
            try {
                byte[] data = Base64.getDecoder().decode(image.base64());
                storage.store(objectPath, cipher.encryptBytes(data, CONTENT_FIELD, id), ImageService.STORED_CONTENT_TYPE);
                RunArtifact artifact = new RunArtifact();
                artifact.setId(id);
                artifact.setModule(module);
                artifact.setRunId(runId);
                artifact.setDonorCaseId(donorCaseId);
                artifact.setJsonPath(image.jsonPath());
                artifact.setContentType(contentType(data));
                artifact.setObjectPath(objectPath);
                artifact.setSizeBytes(data.length);
                artifacts.save(artifact);
            } catch (RuntimeException e) {
                log.warn("Could not store result image {} of {} run {}: {}", image.jsonPath(), module, runId,
                        e.getClass().getSimpleName());
            }
        }
    }

    /**
     * Puts the run's stored images back into {@code result} (base64, at their JSON paths). An image that
     * cannot be read or decrypted is left out (null) rather than failing the whole run view.
     */
    public JsonNode restore(String module, UUID runId, JsonNode result) {
        if (!(result instanceof ObjectNode root)) {
            return result;
        }
        for (RunArtifact artifact : artifacts.findByModuleAndRunId(module, runId)) {
            try {
                byte[] data = cipher.decryptBytes(storage.read(artifact.getObjectPath()), CONTENT_FIELD, artifact.getId());
                put(root, artifact.getJsonPath(), Base64.getEncoder().encodeToString(data));
            } catch (RuntimeException e) {
                log.warn("Could not restore result image {} of {} run {}: {}", artifact.getJsonPath(), module, runId,
                        e.getClass().getSimpleName());
            }
        }
        return root;
    }

    /** Sets a string at a JSON Pointer such as /images/overlayJpeg or /diseases/0/gradcamPng, creating objects on the way. */
    static void put(ObjectNode root, String pointer, String value) {
        String[] parts = pointer.substring(1).split("/");
        JsonNode node = root;
        for (int i = 0; i < parts.length - 1; i++) {
            String part = parts[i];
            JsonNode next;
            if (node instanceof ArrayNode array) {
                next = array.get(Integer.parseInt(part));
            } else {
                ObjectNode object = (ObjectNode) node;
                next = object.get(part);
                if (next == null || next.isNull()) {
                    next = object.putObject(part);
                }
            }
            node = next;
        }
        String last = parts[parts.length - 1];
        if (node instanceof ObjectNode object) {
            object.put(last, value);
        }
    }

    private static String contentType(byte[] data) {
        if (data.length > 3 && (data[0] & 0xFF) == 0xFF && (data[1] & 0xFF) == 0xD8) {
            return "image/jpeg";
        }
        if (data.length > 8 && (data[0] & 0xFF) == 0x89 && data[1] == 'P' && data[2] == 'N' && data[3] == 'G') {
            return "image/png";
        }
        return "application/octet-stream";
    }
}
