package com.cornealai.backend.analysis.dto.disease;

import com.cornealai.backend.analysis.dto.ImageValidation;

import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Mirrors ml-service's POST /disease/analyze response; {@code analysisId} is added by the backend.
 * {@code status} is "completed", or "input_check_failed" when the input checks failed and the
 * analysis was not forced: then only {@code inputCheck} and {@code imageQuality} are set.
 */
public record DiseaseAnalyzeResponse(
        UUID analysisId,
        String caseId,
        String status,
        String message,
        ImageValidation imageValidation,
        InputCheck inputCheck,
        ImageQuality imageQuality,
        String method,
        List<DiseaseFinding> diseases,
        List<String> detected,
        Boolean normal,
        List<SeverityFinding> severity,
        String overallSeverity,
        Map<String, Double> severityProbabilities,
        Map<String, Double> measurementsUsed,
        List<String> measurementsNotRecorded,
        Boolean reliable
) {

    public static final String INPUT_CHECK_FAILED = "input_check_failed";

    public static DiseaseAnalyzeResponse inputCheckFailed(String caseId, String message, InputCheck inputCheck,
                                                          ImageQuality imageQuality) {
        return new DiseaseAnalyzeResponse(null, caseId, INPUT_CHECK_FAILED, message, null, inputCheck, imageQuality,
                null, null, null, null, null, null, null, null, null, null);
    }

    public DiseaseAnalyzeResponse withCaseId(String id) {
        return new DiseaseAnalyzeResponse(analysisId, id, status, message, imageValidation, inputCheck, imageQuality,
                method, diseases, detected, normal, severity, overallSeverity, severityProbabilities,
                measurementsUsed, measurementsNotRecorded, reliable);
    }

    public DiseaseAnalyzeResponse withAnalysisId(UUID id) {
        return new DiseaseAnalyzeResponse(id, caseId, status, message, imageValidation, inputCheck, imageQuality,
                method, diseases, detected, normal, severity, overallSeverity, severityProbabilities,
                measurementsUsed, measurementsNotRecorded, reliable);
    }

    /** For the audit record: the same response without the (large) Grad-CAM images. */
    public DiseaseAnalyzeResponse withoutGradcam() {
        List<DiseaseFinding> stripped = diseases == null ? null : diseases.stream().map(DiseaseFinding::withoutGradcam).toList();
        return new DiseaseAnalyzeResponse(analysisId, caseId, status, message, imageValidation, inputCheck, imageQuality,
                method, stripped, detected, normal, severity, overallSeverity, severityProbabilities,
                measurementsUsed, measurementsNotRecorded, reliable);
    }
}
