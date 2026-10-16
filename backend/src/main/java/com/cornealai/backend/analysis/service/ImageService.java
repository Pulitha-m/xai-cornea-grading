package com.cornealai.backend.analysis.service;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.dto.ImageUploadResponse;
import com.cornealai.backend.analysis.entity.AnalysisImage;
import com.cornealai.backend.analysis.image.ImageInspector;
import com.cornealai.backend.analysis.repository.AnalysisImageRepository;
import com.cornealai.backend.analysis.storage.ImageStorage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.UUID;

/** Validates and stores uploaded images. Storage paths are generated here, never taken from clients. */
@Service
public class ImageService {

    private static final Logger log = LoggerFactory.getLogger(ImageService.class);
    private static final int MAX_CASE_ID_LENGTH = 100;

    private final ImageInspector inspector;
    private final ImageStorage storage;
    private final AnalysisImageRepository images;

    public ImageService(ImageInspector inspector, ImageStorage storage, AnalysisImageRepository images) {
        this.inspector = inspector;
        this.storage = storage;
        this.images = images;
    }

    public ImageUploadResponse upload(String caseId, byte[] data, Long userId) {
        String cleanCaseId = normalizeCaseId(caseId);
        ImageInspector.InspectedImage inspected = inspector.inspect(data);

        UUID id = UUID.randomUUID();
        String objectPath = folderFor(cleanCaseId) + "/" + id + "." + inspected.extension();
        storage.store(objectPath, data, inspected.contentType());

        AnalysisImage image = new AnalysisImage();
        image.setId(id);
        image.setCaseId(cleanCaseId);
        image.setBucket(storage.bucket());
        image.setObjectPath(objectPath);
        image.setContentType(inspected.contentType());
        image.setSizeBytes(data.length);
        image.setSha256(sha256(data));
        image.setWidth(inspected.width());
        image.setHeight(inspected.height());
        image.setUploadedBy(userId);
        try {
            images.saveAndFlush(image);
        } catch (RuntimeException e) {
            // Do not leave an orphaned object if the record could not be saved.
            try {
                storage.delete(objectPath);
            } catch (RuntimeException cleanup) {
                log.warn("Could not remove orphaned image object {}", id);
            }
            throw e;
        }

        return new ImageUploadResponse(id, cleanCaseId, inspected.contentType(), data.length,
                inspected.width(), inspected.height());
    }

    static String normalizeCaseId(String caseId) {
        String trimmed = caseId == null ? "" : caseId.trim();
        if (trimmed.isEmpty() || trimmed.length() > MAX_CASE_ID_LENGTH) {
            throw new AnalysisRejectedException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "caseId",
                    "Enter a case ID of at most " + MAX_CASE_ID_LENGTH + " characters.");
        }
        return trimmed;
    }

    /** A storage-safe folder name derived from the case id (letters, digits, dot, dash, underscore). */
    static String folderFor(String caseId) {
        String folder = caseId.replaceAll("[^A-Za-z0-9._-]", "_");
        return folder.matches("\\.+") ? "_" : folder;
    }

    static String sha256(byte[] data) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(data));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
