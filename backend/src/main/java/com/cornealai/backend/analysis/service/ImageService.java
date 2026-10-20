package com.cornealai.backend.analysis.service;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.dto.ImageUploadResponse;
import com.cornealai.backend.analysis.entity.AnalysisImage;
import com.cornealai.backend.analysis.image.ImageInspector;
import com.cornealai.backend.analysis.repository.AnalysisImageRepository;
import com.cornealai.backend.analysis.storage.ImageStorage;
import com.cornealai.backend.cases.TissueNumber;
import com.cornealai.backend.cases.entity.DonorCase;
import com.cornealai.backend.cases.service.DonorCaseService;
import com.cornealai.backend.common.crypto.CryptoException;
import com.cornealai.backend.common.crypto.FieldCipher;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.UUID;

/**
 * Validates, encrypts and stores uploaded images, and reads them back verified. Storage paths are
 * generated here, never taken from clients, and contain only the image id (no case id or format).
 *
 * <p>Images are encrypted with {@link FieldCipher} for {@link #CONTENT_FIELD} and the image id; the
 * GCM tag is the integrity check, so a changed object, or another image's object, fails to read.
 */
@Service
public class ImageService {

    /** Field name bound into every encrypted image. */
    public static final String CONTENT_FIELD = "analysis_images.content";
    static final String STORED_CONTENT_TYPE = "application/octet-stream";

    private static final Logger log = LoggerFactory.getLogger(ImageService.class);

    private final ImageInspector inspector;
    private final ImageStorage storage;
    private final AnalysisImageRepository images;
    private final FieldCipher cipher;
    private final DonorCaseService donorCases;

    public ImageService(ImageInspector inspector, ImageStorage storage, AnalysisImageRepository images,
                        FieldCipher cipher, DonorCaseService donorCases) {
        this.inspector = inspector;
        this.storage = storage;
        this.images = images;
        this.cipher = cipher;
        this.donorCases = donorCases;
    }

    /**
     * Stores an image for the donor case with this tissue ID (created on first use). The image record
     * refers to the case by its UUID; the tissue ID itself is only returned to the uploader.
     */
    public ImageUploadResponse upload(String tissueId, byte[] data, Long userId) {
        TissueNumber tissue = TissueNumber.parse(tissueId);
        return store(data, userId, tissue, () -> donorCases.findOrCreate(tissue, userId));
    }

    /** Stores an image for an existing donor case (the case workspace). */
    public ImageUploadResponse uploadToCase(DonorCase donorCase, byte[] data, Long userId) {
        return store(data, userId, donorCases.tissueNumberOf(donorCase), () -> donorCase);
    }

    /** The image record, or 404. Callers check that it belongs to the case they were given. */
    public AnalysisImage requireImage(UUID imageId) {
        return images.findById(imageId)
                .orElseThrow(() -> new AnalysisRejectedException(HttpStatus.NOT_FOUND, "IMAGE_NOT_FOUND", "imageId",
                        "The image was not found. Upload it again."));
    }

    /** The case is resolved only after the image passed inspection and was stored, so a rejected upload creates no case. */
    private ImageUploadResponse store(byte[] data, Long userId, TissueNumber tissue,
                                      java.util.function.Supplier<DonorCase> caseFor) {
        ImageInspector.InspectedImage inspected = inspector.inspect(data);

        UUID id = UUID.randomUUID();
        String objectPath = objectPathFor(id);
        storage.store(objectPath, cipher.encryptBytes(data, CONTENT_FIELD, id), STORED_CONTENT_TYPE);

        try {
            DonorCase donorCase = caseFor.get();
            AnalysisImage image = new AnalysisImage();
            image.setId(id);
            image.setCaseId(donorCase.getId().toString());
            image.setDonorCaseId(donorCase.getId());
            image.setBucket(storage.bucket());
            image.setObjectPath(objectPath);
            image.setContentType(inspected.contentType());
            image.setSizeBytes(data.length);
            image.setEncrypted(true);
            image.setWidth(inspected.width());
            image.setHeight(inspected.height());
            image.setUploadedBy(userId);
            images.saveAndFlush(image);
        } catch (RuntimeException e) {
            // Do not leave an orphaned object if the case or the record could not be saved.
            try {
                storage.delete(objectPath);
            } catch (RuntimeException cleanup) {
                log.warn("Could not remove orphaned image object {}", id);
            }
            throw e;
        }

        return new ImageUploadResponse(id, tissue.value(), inspected.contentType(), data.length,
                inspected.width(), inspected.height());
    }

    /**
     * The image's original bytes, read from storage and verified: decrypted (which authenticates them)
     * or, for an image stored before encryption, checked against its SHA-256.
     */
    public byte[] readVerified(AnalysisImage image) {
        byte[] stored = storage.read(image.getObjectPath());
        if (stored != null) {
            if (!image.isEncrypted()) {
                if (image.getSha256() != null && sha256(stored).equals(image.getSha256())) {
                    return stored;
                }
            } else {
                try {
                    return cipher.decryptBytes(stored, CONTENT_FIELD, image.getId());
                } catch (CryptoException e) {
                    log.warn("Stored image {} failed decryption: {}", image.getId(), e.getMessage());
                }
            }
        }
        throw new AnalysisRejectedException(HttpStatus.BAD_GATEWAY, "IMAGE_STORAGE_ACCESS_FAILED", null,
                "The stored image could not be verified. Upload it again.");
    }

    static String objectPathFor(UUID imageId) {
        return "images/" + imageId;
    }

    static String sha256(byte[] data) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(data));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
