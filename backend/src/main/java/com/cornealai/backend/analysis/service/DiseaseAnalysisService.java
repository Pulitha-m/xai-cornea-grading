package com.cornealai.backend.analysis.service;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.disease.DiseaseAnalyzeRequest;
import com.cornealai.backend.analysis.dto.disease.DiseaseAnalyzeResponse;
import com.cornealai.backend.analysis.entity.AnalysisImage;
import com.cornealai.backend.analysis.entity.DiseaseAnalysisRun;
import com.cornealai.backend.analysis.repository.DiseaseAnalysisRunRepository;
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
 * Runs the v2 disease detection and severity models on a stored image of a donor case. Same access
 * policy as {@link GradingAnalysisService}: any clinical user, the image must belong to the case, its
 * bytes are read server-side and verified (decrypted, see ImageService). Every attempt is recorded.
 */
@Service
public class DiseaseAnalysisService {

    private static final Logger log = LoggerFactory.getLogger(DiseaseAnalysisService.class);

    private final DiseaseAnalysisRunRepository runs;
    private final ImageService imageService;
    private final DonorCaseService donorCases;
    private final MlServiceClient mlServiceClient;
    private final ObjectMapper objectMapper;

    public DiseaseAnalysisService(
            DiseaseAnalysisRunRepository runs,
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

    /** The module page: the case is named by tissue ID and the measurements are entered with the request. */
    public DiseaseAnalyzeResponse analyze(DiseaseAnalyzeRequest request, Long userId) {
        TissueNumber tissue = TissueNumber.parse(request.caseId());
        AnalysisImage image = imageService.requireImage(request.imageId());
        DonorCase donorCase = donorCases.requireCaseOf(image, tissue);
        return run(donorCase, image, request.measurements(), request.force(), null, userId).withCaseId(tissue.value());
    }

    /**
     * Analyses {@code image} of {@code donorCase} (already resolved and checked by the caller) and records
     * the run. The response carries the case UUID as {@code caseId}.
     */
    public DiseaseAnalyzeResponse run(DonorCase donorCase, AnalysisImage image, Map<String, Object> measurements,
                                      boolean force, UUID caseAnalysisId, Long userId) {
        String caseId = donorCase.getId().toString();
        DiseaseAnalysisRun run = new DiseaseAnalysisRun();
        run.setId(UUID.randomUUID());
        run.setImageId(image.getId());
        run.setCaseId(caseId);
        run.setDonorCaseId(donorCase.getId());
        run.setCaseAnalysisId(caseAnalysisId);
        run.setRequestedBy(userId);
        run.setForced(force);
        String measurementsJson = objectMapper.writeValueAsString(measurements);
        run.setMeasurementsJson(measurementsJson);

        try {
            byte[] data = imageService.readVerified(image);
            String filename = image.getId() + (image.getContentType().equals("image/png") ? ".png" : ".jpg");
            DiseaseAnalyzeResponse result = mlServiceClient.analyzeDisease(caseId, measurementsJson, force,
                    data, filename);
            if (result == null || result.status() == null
                    || (!DiseaseAnalyzeResponse.INPUT_CHECK_FAILED.equals(result.status()) && result.diseases() == null)) {
                throw new AnalysisRejectedException(HttpStatus.BAD_GATEWAY, "MODEL_INFERENCE_FAILED", null,
                        "The analysis could not be completed. Try again later.");
            }
            DiseaseAnalyzeResponse response = result.withAnalysisId(run.getId()).withCaseId(caseId);

            run.setStatus(response.status());
            run.setResultJson(objectMapper.writeValueAsString(response.withoutGradcam()));
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
    private void record(DiseaseAnalysisRun run, String status, String errorCode) {
        run.setStatus(status);
        run.setErrorCode(errorCode);
        try {
            runs.save(run);
        } catch (RuntimeException e) {
            log.error("Could not record {} disease run {}", status, run.getId(), e);
        }
    }
}
