package com.cornealai.backend.analysis.service;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.AnalyzeRequest;
import com.cornealai.backend.analysis.dto.AnalyzeResponse;
import com.cornealai.backend.analysis.entity.AnalysisImage;
import com.cornealai.backend.analysis.entity.AnalysisRun;
import com.cornealai.backend.analysis.repository.AnalysisImageRepository;
import com.cornealai.backend.cases.TissueNumber;
import com.cornealai.backend.cases.entity.DonorCase;
import com.cornealai.backend.cases.service.DonorCaseService;
import com.cornealai.backend.analysis.repository.AnalysisRunRepository;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import tools.jackson.databind.ObjectMapper;

import java.util.UUID;

/**
 * Runs an analysis on a stored image. The image is resolved from its id only after
 * checking that the caller uploaded it, then its bytes are read server-side and sent
 * to ml-service. Every attempt is recorded, including rejections.
 */
@Service
public class AnalysisService {

    private final AnalysisImageRepository images;
    private final AnalysisRunRepository runs;
    private final ImageService imageService;
    private final DonorCaseService donorCases;
    private final MlServiceClient mlServiceClient;
    private final ObjectMapper objectMapper;

    public AnalysisService(
            AnalysisImageRepository images,
            AnalysisRunRepository runs,
            ImageService imageService,
            DonorCaseService donorCases,
            MlServiceClient mlServiceClient,
            ObjectMapper objectMapper
    ) {
        this.images = images;
        this.runs = runs;
        this.imageService = imageService;
        this.donorCases = donorCases;
        this.mlServiceClient = mlServiceClient;
        this.objectMapper = objectMapper;
    }

    public AnalyzeResponse analyze(AnalyzeRequest request, Long userId) {
        TissueNumber tissue = TissueNumber.parse(request.caseId());
        AnalysisImage image = images.findById(request.imageId())
                .orElseThrow(() -> new AnalysisRejectedException(HttpStatus.NOT_FOUND, "IMAGE_NOT_FOUND", "imageId",
                        "The image was not found. Upload it again."));

        // Access policy: only the user who uploaded an image may analyse it.
        if (!image.getUploadedBy().equals(userId)) {
            throw new AnalysisRejectedException(HttpStatus.FORBIDDEN, "TISSUE_ACCESS_DENIED", "imageId",
                    "You do not have access to this image.");
        }
        DonorCase donorCase = donorCases.requireCaseOf(image, tissue);
        String caseId = donorCase.getId().toString();

        AnalysisRun run = new AnalysisRun();
        run.setId(UUID.randomUUID());
        run.setImageId(image.getId());
        run.setCaseId(caseId);
        run.setDonorCaseId(donorCase.getId());
        run.setRequestedBy(userId);
        String featuresJson = objectMapper.writeValueAsString(request.clinicalFeatures());
        run.setClinicalFeaturesJson(featuresJson);
        if (request.clinicalFeatures().get("ECD_CD_cells_per_mm2") instanceof Number ecd) {
            run.setEcd(ecd.doubleValue());
        }

        try {
            byte[] data = imageService.readVerified(image);
            String filename = image.getId() + (image.getContentType().equals("image/png") ? ".png" : ".jpg");
            AnalyzeResponse result = mlServiceClient.analyze(caseId, featuresJson, data, filename);
            if (result == null || result.status() == null || result.grading() == null) {
                throw new AnalysisRejectedException(HttpStatus.BAD_GATEWAY, "MODEL_INFERENCE_FAILED", null,
                        "The analysis could not be completed. Try again later.");
            }
            AnalyzeResponse response = result.withAnalysisId(run.getId()).withCaseId(caseId);  // stored with the case UUID only

            run.setStatus(response.status());
            run.setResultJson(objectMapper.writeValueAsString(response));
            runs.save(run);
            return response.withCaseId(tissue.value());
        } catch (AnalysisRejectedException e) {
            run.setStatus("rejected");
            run.setErrorCode(e.getCode());
            runs.save(run);
            throw e;
        }
    }
}
