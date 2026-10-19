package com.cornealai.backend.analysis.dto.cellular;

import com.cornealai.backend.analysis.dto.ImageValidation;

import java.util.List;
import java.util.UUID;

/**
 * Mirrors ml-service's POST /cellular/analyze response; {@code analysisId} is added by the backend.
 * A completed analysis can still be not {@code reliable} (a quality flag of level "error", e.g. too few cells).
 */
public record CellularAnalyzeResponse(
        UUID analysisId,
        String caseId,
        String status,
        String message,
        ImageValidation imageValidation,
        String method,
        Double umPerPx,
        Boolean validatedImageSize,
        CellularBiomarkers biomarkers,
        CellularRoi roi,
        List<QualityFlag> qualityFlags,
        Boolean reliable,
        CellularUncertainty uncertainty,
        CellularEvidence evidence,
        CellularReliability reliability,
        CellularImages images,
        Double seconds
) {

    public CellularAnalyzeResponse withAnalysisId(UUID id) {
        return new CellularAnalyzeResponse(id, caseId, status, message, imageValidation, method, umPerPx,
                validatedImageSize, biomarkers, roi, qualityFlags, reliable, uncertainty, evidence, reliability,
                images, seconds);
    }

    /** For the audit record: the same response without the (large) overlay images. */
    public CellularAnalyzeResponse withoutImages() {
        return new CellularAnalyzeResponse(analysisId, caseId, status, message, imageValidation, method, umPerPx,
                validatedImageSize, biomarkers, roi, qualityFlags, reliable, uncertainty, evidence, reliability,
                null, seconds);
    }
}
