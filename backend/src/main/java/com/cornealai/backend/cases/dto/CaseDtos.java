package com.cornealai.backend.cases.dto;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;
import tools.jackson.databind.JsonNode;

import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/** Request and response bodies of the donor case API (/api/cases). */
public final class CaseDtos {

    private CaseDtos() {
    }

    /** Opens the case for a tissue ID such as 12656R, creating it on first use. */
    public record CreateCaseRequest(@NotBlank @Size(max = 20) String tissueId) {
    }

    /**
     * Case details entered once and used by every module: donor information, the six Konan measurements
     * and the slit-lamp findings (by grading feature name; null or absent = not recorded).
     */
    public record CaseDetails(
            @PositiveOrZero @Max(120) Integer donorAgeYears,
            @PositiveOrZero Double deathToPreservationHours,
            LocalDate preservationDate,
            @Positive Double ecd,
            @Positive Double cv,
            @Positive @DecimalMax("100") Double hexPercent,
            @Positive Double sd,
            @Positive Integer totalCellCount,
            @Positive Double totalAreaUm2,
            @Size(max = 18) Map<String, Object> slitLamp
    ) {
    }

    public record CaseResponse(
            UUID id,
            String tissueId,
            CaseDetails details,
            long imageCount,
            SignoffSummary latestSignoff,
            Instant createdAt,
            Instant updatedAt
    ) {
    }

    /** What a specialist confirmed. Grades as the eye bank grades them; findings as recommendation uses them. */
    public record SignoffRequest(
            @NotBlank @Pattern(regexp = "A\\+|A|B|C") String confirmedGrade,
            @NotBlank @Pattern(regexp = "Normal|Folds|Guttata|FECD|Other") String diseaseFinding,
            @Positive Double ecd,
            @Positive Double cv,
            @Positive @DecimalMax("100") Double hexPercent,
            @Size(max = 2000) String notes,
            UUID caseAnalysisId
    ) {
    }

    public record Signoff(
            UUID id,
            String confirmedGrade,
            String diseaseFinding,
            Double ecd,
            Double cv,
            Double hexPercent,
            String notes,
            Long signedBy,
            String signedByName,
            UUID caseAnalysisId,
            Instant createdAt
    ) {
    }

    /** The current sign-off, shown with the case (no notes). */
    public record SignoffSummary(String confirmedGrade, String diseaseFinding, String signedByName, Instant createdAt) {
    }

    /** Serology results: each "Negative", "Positive" or "Unknown" (null = not recorded). Doctors only. */
    public record Serology(
            @Pattern(regexp = "Negative|Positive|Unknown") String hiv,
            @Pattern(regexp = "Negative|Positive|Unknown") String hbv,
            @Pattern(regexp = "Negative|Positive|Unknown") String hcv,
            @Pattern(regexp = "Negative|Positive|Unknown") String syphilis,
            Boolean serologyClear
    ) {
    }

    /**
     * A signed-off cornea as a recommendation candidate, in the recommendation module's MatchCandidate
     * fields. {@code recordId} is the case UUID (sent onwards); {@code tissueId} is for display only.
     */
    public record MatchCandidateView(
            String recordId,
            String tissueId,
            String grade,
            Double ecd,
            Double cv,
            Double hex,
            Double donorAge,
            Double deathToPreservationH,
            Double daysInStorage,
            String serologyClear,
            String diseaseFinding
    ) {
    }

    public record CaseImage(
            UUID id,
            String contentType,
            long sizeBytes,
            int width,
            int height,
            Long uploadedBy,
            Instant uploadedAt
    ) {
    }

    /**
     * Runs the chosen modules (cellular, grading, disease) on one of the case's images. {@code forceDisease}
     * (optional, default false) runs the disease models even if their input checks fail.
     */
    public record CaseAnalysisRequest(
            @NotNull UUID imageId,
            @NotEmpty @Size(max = 3) Set<String> modules,
            Boolean forceDisease
    ) {

        public boolean force() {
            return Boolean.TRUE.equals(forceDisease);
        }
    }

    /** One module's outcome: "completed" with its result, or "rejected" / "failed" with a code and message. */
    public record ModuleOutcome(String status, String errorCode, String message, Object result) {

        public static ModuleOutcome completed(Object result) {
            return new ModuleOutcome("completed", null, null, result);
        }

        public static ModuleOutcome notRun(String status, String errorCode, String message) {
            return new ModuleOutcome(status, errorCode, message, null);
        }
    }

    /** A disagreement between modules, for the reviewer; it never changes a result. */
    public record ConsistencyFlag(String code, String message) {
    }

    public record CaseAnalysisResponse(
            UUID id,
            String tissueId,
            UUID imageId,
            Map<String, ModuleOutcome> modules,
            List<ConsistencyFlag> consistency,
            Instant createdAt
    ) {
    }

    /** A saved run of any module, newest first; {@code headline} holds the few values worth listing. */
    public record RunSummary(
            UUID id,
            String module,
            String status,
            String errorCode,
            UUID imageId,
            UUID caseAnalysisId,
            Instant createdAt,
            Map<String, Object> headline
    ) {
    }

    /** A saved run with the inputs it was given and the stored result (image maps are not stored). */
    public record RunDetail(RunSummary summary, JsonNode inputs, JsonNode result) {
    }
}
