package com.cornealai.backend.analysis.service;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.grading.GradingAnalyzeRequest;
import com.cornealai.backend.analysis.dto.grading.GradingAnalyzeResponse;
import com.cornealai.backend.analysis.entity.AnalysisImage;
import com.cornealai.backend.analysis.entity.GradingAnalysisRun;
import com.cornealai.backend.analysis.repository.GradingAnalysisRunRepository;
import com.cornealai.backend.cases.TissueNumber;
import com.cornealai.backend.cases.entity.DonorCase;
import com.cornealai.backend.cases.service.DonorCaseService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import tools.jackson.databind.ObjectMapper;

import java.util.Map;
import java.util.UUID;

/**
 * Runs the hybrid grading model on a stored image of a donor case. Any clinical user may analyse
 * any case; the image must belong to the case named. Its bytes are read server-side and verified
 * (decrypted, see ImageService). Every attempt is recorded, including rejections and failures
 * (without the explanation's image maps).
 */
@Service
public class GradingAnalysisService {

    private static final Logger log = LoggerFactory.getLogger(GradingAnalysisService.class);

    private final GradingAnalysisRunRepository runs;
    private final ImageService imageService;
    private final DonorCaseService donorCases;
    private final MlServiceClient mlServiceClient;
    private final ObjectMapper objectMapper;

    public GradingAnalysisService(
            GradingAnalysisRunRepository runs,
            ImageService imageService,
            DonorCaseService donorCases,
            MlServiceClient mlServiceClient,
            ObjectMapper objectMapper
    ) {
        this.runs = runs;
        this.imageService = imageService;
        this.donorCases = donorCases;
        this.mlServiceClient = mlServiceClient;
        this.objectMapper = objectMapper;
    }

    /** The module page: the case is named by tissue ID and the features are entered with the request. */
    public GradingAnalyzeResponse analyze(GradingAnalyzeRequest request, Long userId) {
        TissueNumber tissue = TissueNumber.parse(request.caseId());
        AnalysisImage image = imageService.requireImage(request.imageId());
        DonorCase donorCase = donorCases.requireCaseOf(image, tissue);
        return run(donorCase, image, request.clinicalFeatures(), null, userId).withCaseId(tissue.value());
    }

    /**
     * Grades {@code image} of {@code donorCase} (already resolved and checked by the caller) and records
     * the run. The response carries the case UUID as {@code caseId}.
     */
    public GradingAnalyzeResponse run(DonorCase donorCase, AnalysisImage image, Map<String, Object> clinicalFeatures,
                                      UUID caseAnalysisId, Long userId) {
        String caseId = donorCase.getId().toString();
        GradingAnalysisRun run = new GradingAnalysisRun();
        run.setId(UUID.randomUUID());
        run.setImageId(image.getId());
        run.setCaseId(caseId);
        run.setDonorCaseId(donorCase.getId());
        run.setCaseAnalysisId(caseAnalysisId);
        run.setRequestedBy(userId);
        String featuresJson = objectMapper.writeValueAsString(clinicalFeatures);
        run.setClinicalFeaturesJson(featuresJson);
        if (clinicalFeatures.get("ECD_CD_cells_per_mm2") instanceof Number ecd) {
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
            GradingAnalyzeResponse response = result.withAnalysisId(run.getId()).withCaseId(caseId);

            run.setStatus(response.status());
            run.setGrade(response.grade());
            run.setResultJson(objectMapper.writeValueAsString(response.withoutImageMaps()));
            runs.save(run);
            return response;
        } catch (AnalysisRejectedException e) {
            record(run, "rejected", e.getCode());
            throw e;
        } catch (RuntimeException e) {
            record(run, "failed", "INTERNAL_ERROR");
            throw e;
        }
    }

    /** Records an unsuccessful attempt; if even that fails (e.g. the database is unreachable), log and move on. */
    private void record(GradingAnalysisRun run, String status, String errorCode) {
        run.setStatus(status);
        run.setErrorCode(errorCode);
        try {
            runs.save(run);
        } catch (RuntimeException e) {
            log.error("Could not record {} grading run {}", status, run.getId(), e);
        }
    }
}
