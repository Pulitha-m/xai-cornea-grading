package com.cornealai.backend.analysis.service;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.cellular.CellularAnalyzeRequest;
import com.cornealai.backend.analysis.dto.cellular.CellularAnalyzeResponse;
import com.cornealai.backend.analysis.dto.cellular.CellularBiomarkers;
import com.cornealai.backend.analysis.entity.AnalysisImage;
import com.cornealai.backend.analysis.entity.CellularAnalysisRun;
import com.cornealai.backend.analysis.repository.AnalysisImageRepository;
import com.cornealai.backend.analysis.repository.CellularAnalysisRunRepository;
import com.cornealai.backend.analysis.storage.ImageStorage;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import tools.jackson.databind.ObjectMapper;

import java.util.UUID;

/**
 * Runs the cellular analysis on a stored image, with the same access policy as {@link AnalysisService}: only the
 * uploader may analyse an image, its bytes are read server-side and checked against the stored SHA-256. Every
 * attempt is recorded (the numbers; the overlay images are not stored).
 */
@Service
public class CellularAnalysisService {

    private final AnalysisImageRepository images;
    private final CellularAnalysisRunRepository runs;
    private final ImageStorage storage;
    private final MlServiceClient mlServiceClient;
    private final ObjectMapper objectMapper;

    public CellularAnalysisService(
            AnalysisImageRepository images,
            CellularAnalysisRunRepository runs,
            ImageStorage storage,
            MlServiceClient mlServiceClient,
            ObjectMapper objectMapper
    ) {
        this.images = images;
        this.runs = runs;
        this.storage = storage;
        this.mlServiceClient = mlServiceClient;
        this.objectMapper = objectMapper;
    }

    public CellularAnalyzeResponse analyze(CellularAnalyzeRequest request, Long userId) {
        String caseId = ImageService.normalizeCaseId(request.caseId());
        AnalysisImage image = images.findById(request.imageId())
                .orElseThrow(() -> new AnalysisRejectedException(HttpStatus.NOT_FOUND, "IMAGE_NOT_FOUND", "imageId",
                        "The image was not found. Upload it again."));

        if (!image.getUploadedBy().equals(userId)) {
            throw new AnalysisRejectedException(HttpStatus.FORBIDDEN, "TISSUE_ACCESS_DENIED", "imageId",
                    "You do not have access to this image.");
        }
        if (!image.getCaseId().equals(caseId)) {
            throw new AnalysisRejectedException(HttpStatus.FORBIDDEN, "TISSUE_ACCESS_DENIED", "caseId",
                    "The image belongs to a different case.");
        }

        CellularAnalysisRun run = new CellularAnalysisRun();
        run.setId(UUID.randomUUID());
        run.setImageId(image.getId());
        run.setCaseId(caseId);
        run.setRequestedBy(userId);

        try {
            byte[] data = storage.read(image.getObjectPath());
            if (data == null || !ImageService.sha256(data).equals(image.getSha256())) {
                throw new AnalysisRejectedException(HttpStatus.BAD_GATEWAY, "IMAGE_STORAGE_ACCESS_FAILED", null,
                        "The stored image could not be verified. Upload it again.");
            }
            String filename = image.getId() + (image.getContentType().equals("image/png") ? ".png" : ".jpg");
            CellularAnalyzeResponse result = mlServiceClient.analyzeCellular(caseId, data, filename);
            if (result == null || result.status() == null || result.biomarkers() == null
                    || result.biomarkers().cellCount() == null) {
                throw new AnalysisRejectedException(HttpStatus.BAD_GATEWAY, "MODEL_INFERENCE_FAILED", null,
                        "The cellular analysis could not be completed. Try again later.");
            }
            CellularAnalyzeResponse response = result.withAnalysisId(run.getId());

            CellularBiomarkers bm = response.biomarkers();
            run.setStatus(response.status());
            run.setCellCount(bm.cellCount());
            run.setEcd(bm.ecd());
            run.setCv(bm.coefficientOfVariation());
            run.setHex(bm.hexagonality());
            run.setReliable(response.reliable());
            run.setResultJson(objectMapper.writeValueAsString(response.withoutImages()));
            runs.save(run);
            return response;
        } catch (AnalysisRejectedException e) {
            run.setStatus("rejected");
            run.setErrorCode(e.getCode());
            runs.save(run);
            throw e;
        }
    }
}
