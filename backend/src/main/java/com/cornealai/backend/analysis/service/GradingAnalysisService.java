package com.cornealai.backend.analysis.service;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.grading.GradingAnalyzeRequest;
import com.cornealai.backend.analysis.dto.grading.GradingAnalyzeResponse;
import com.cornealai.backend.analysis.entity.AnalysisImage;
import com.cornealai.backend.analysis.entity.GradingAnalysisRun;
import com.cornealai.backend.analysis.repository.AnalysisImageRepository;
import com.cornealai.backend.cases.TissueNumber;
import com.cornealai.backend.cases.entity.DonorCase;
import com.cornealai.backend.cases.service.DonorCaseService;
import com.cornealai.backend.analysis.repository.GradingAnalysisRunRepository;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import tools.jackson.databind.ObjectMapper;

import java.util.UUID;

/**
 * Runs the hybrid grading model on a stored image, with the same access policy as
 * {@link AnalysisService}: only the uploader may analyse an image, its bytes are read
 * server-side and verified (decrypted, see ImageService). Every attempt is recorded (without the
 * explanation's image maps).
 */
@Service
public class GradingAnalysisService {

    private final AnalysisImageRepository images;
    private final GradingAnalysisRunRepository runs;
    private final ImageService imageService;
    private final DonorCaseService donorCases;
    private final MlServiceClient mlServiceClient;
    private final ObjectMapper objectMapper;

    public GradingAnalysisService(
            AnalysisImageRepository images,
            GradingAnalysisRunRepository runs,
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

    public GradingAnalyzeResponse analyze(GradingAnalyzeRequest request, Long userId) {
        TissueNumber tissue = TissueNumber.parse(request.caseId());
        AnalysisImage image = images.findById(request.imageId())
                .orElseThrow(() -> new AnalysisRejectedException(HttpStatus.NOT_FOUND, "IMAGE_NOT_FOUND", "imageId",
                        "The image was not found. Upload it again."));

        if (!image.getUploadedBy().equals(userId)) {
            throw new AnalysisRejectedException(HttpStatus.FORBIDDEN, "TISSUE_ACCESS_DENIED", "imageId",
                    "You do not have access to this image.");
        }
        DonorCase donorCase = donorCases.requireCaseOf(image, tissue);
        String caseId = donorCase.getId().toString();

        GradingAnalysisRun run = new GradingAnalysisRun();
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
            GradingAnalyzeResponse result = mlServiceClient.analyzeGrading(caseId, featuresJson, data, filename);
            if (result == null || result.status() == null || result.grade() == null) {
                throw new AnalysisRejectedException(HttpStatus.BAD_GATEWAY, "MODEL_INFERENCE_FAILED", null,
                        "The grading could not be completed. Try again later.");
            }
            GradingAnalyzeResponse response = result.withAnalysisId(run.getId()).withCaseId(caseId);  // stored with the case UUID only

            run.setStatus(response.status());
            run.setGrade(response.grade());
            run.setResultJson(objectMapper.writeValueAsString(response.withoutImageMaps()));
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
