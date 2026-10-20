package com.cornealai.backend.analysis.service;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.cellular.CellularAnalyzeRequest;
import com.cornealai.backend.analysis.dto.cellular.CellularAnalyzeResponse;
import com.cornealai.backend.analysis.dto.cellular.CellularBiomarkers;
import com.cornealai.backend.analysis.entity.AnalysisImage;
import com.cornealai.backend.analysis.entity.CellularAnalysisRun;
import com.cornealai.backend.analysis.repository.CellularAnalysisRunRepository;
import com.cornealai.backend.cases.TissueNumber;
import com.cornealai.backend.cases.entity.DonorCase;
import com.cornealai.backend.cases.service.DonorCaseService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import tools.jackson.databind.ObjectMapper;

import java.util.UUID;

/**
 * Runs the cellular analysis on a stored image of a donor case. Same access policy as
 * {@link GradingAnalysisService}: any clinical user, the image must belong to the case, its bytes are
 * read server-side and verified (decrypted, see ImageService). Every attempt is recorded (the numbers;
 * the overlay images are not stored). Its output feeds no other module.
 */
@Service
public class CellularAnalysisService {

    private static final Logger log = LoggerFactory.getLogger(CellularAnalysisService.class);

    private final CellularAnalysisRunRepository runs;
    private final ImageService imageService;
    private final DonorCaseService donorCases;
    private final MlServiceClient mlServiceClient;
    private final ObjectMapper objectMapper;

    public CellularAnalysisService(
            CellularAnalysisRunRepository runs,
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

    /** The module page: the case is named by tissue ID. */
    public CellularAnalyzeResponse analyze(CellularAnalyzeRequest request, Long userId) {
        TissueNumber tissue = TissueNumber.parse(request.caseId());
        AnalysisImage image = imageService.requireImage(request.imageId());
        DonorCase donorCase = donorCases.requireCaseOf(image, tissue);
        return run(donorCase, image, null, userId).withCaseId(tissue.value());
    }

    /**
     * Analyses {@code image} of {@code donorCase} (already resolved and checked by the caller) and records
     * the run. The response carries the case UUID as {@code caseId}.
     */
    public CellularAnalyzeResponse run(DonorCase donorCase, AnalysisImage image, UUID caseAnalysisId, Long userId) {
        String caseId = donorCase.getId().toString();
        CellularAnalysisRun run = new CellularAnalysisRun();
        run.setId(UUID.randomUUID());
        run.setImageId(image.getId());
        run.setCaseId(caseId);
        run.setDonorCaseId(donorCase.getId());
        run.setCaseAnalysisId(caseAnalysisId);
        run.setRequestedBy(userId);

        try {
            byte[] data = imageService.readVerified(image);
            String filename = image.getId() + (image.getContentType().equals("image/png") ? ".png" : ".jpg");
            CellularAnalyzeResponse result = mlServiceClient.analyzeCellular(caseId, data, filename);
            if (result == null || result.status() == null || result.biomarkers() == null
                    || result.biomarkers().cellCount() == null) {
                throw new AnalysisRejectedException(HttpStatus.BAD_GATEWAY, "MODEL_INFERENCE_FAILED", null,
                        "The cellular analysis could not be completed. Try again later.");
            }
            CellularAnalyzeResponse response = result.withAnalysisId(run.getId()).withCaseId(caseId);

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
            record(run, "rejected", e.getCode());
            throw e;
        } catch (RuntimeException e) {
            record(run, "failed", "INTERNAL_ERROR");
            throw e;
        }
    }

    /** Records an unsuccessful attempt; if even that fails (e.g. the database is unreachable), log and move on. */
    private void record(CellularAnalysisRun run, String status, String errorCode) {
        run.setStatus(status);
        run.setErrorCode(errorCode);
        try {
            runs.save(run);
        } catch (RuntimeException e) {
            log.error("Could not record {} cellular run {}", status, run.getId(), e);
        }
    }
}
