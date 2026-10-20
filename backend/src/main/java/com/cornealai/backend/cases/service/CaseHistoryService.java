package com.cornealai.backend.cases.service;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.entity.AnalysisRun;
import com.cornealai.backend.analysis.entity.CellularAnalysisRun;
import com.cornealai.backend.analysis.entity.DiseaseAnalysisRun;
import com.cornealai.backend.analysis.entity.GradingAnalysisRun;
import com.cornealai.backend.analysis.repository.AnalysisRunRepository;
import com.cornealai.backend.analysis.repository.CellularAnalysisRunRepository;
import com.cornealai.backend.analysis.repository.DiseaseAnalysisRunRepository;
import com.cornealai.backend.analysis.repository.GradingAnalysisRunRepository;
import com.cornealai.backend.cases.dto.CaseDtos.RunDetail;
import com.cornealai.backend.cases.dto.CaseDtos.RunSummary;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** Every saved run of a donor case, across modules, newest first; and one run in full. */
@Service
public class CaseHistoryService {

    private final DonorCaseService donorCases;
    private final CellularAnalysisRunRepository cellularRuns;
    private final GradingAnalysisRunRepository gradingRuns;
    private final DiseaseAnalysisRunRepository diseaseRuns;
    private final AnalysisRunRepository combinedRuns;
    private final ObjectMapper objectMapper;

    public CaseHistoryService(DonorCaseService donorCases, CellularAnalysisRunRepository cellularRuns,
                              GradingAnalysisRunRepository gradingRuns, DiseaseAnalysisRunRepository diseaseRuns,
                              AnalysisRunRepository combinedRuns, ObjectMapper objectMapper) {
        this.donorCases = donorCases;
        this.cellularRuns = cellularRuns;
        this.gradingRuns = gradingRuns;
        this.diseaseRuns = diseaseRuns;
        this.combinedRuns = combinedRuns;
        this.objectMapper = objectMapper;
    }

    public List<RunSummary> runs(UUID caseId) {
        donorCases.require(caseId);
        List<RunSummary> all = new ArrayList<>();
        cellularRuns.findByDonorCaseIdOrderByCreatedAtDesc(caseId).forEach(r -> all.add(summary(r)));
        gradingRuns.findByDonorCaseIdOrderByCreatedAtDesc(caseId).forEach(r -> all.add(summary(r)));
        diseaseRuns.findByDonorCaseIdOrderByCreatedAtDesc(caseId).forEach(r -> all.add(summary(r)));
        combinedRuns.findByDonorCaseIdOrderByCreatedAtDesc(caseId).forEach(r -> all.add(summary(r)));
        all.sort(Comparator.comparing(RunSummary::createdAt).reversed());
        return all;
    }

    /** One run of this case; 404 when it does not exist or belongs to another case. */
    public RunDetail run(UUID caseId, String module, UUID runId) {
        return switch (module) {
            case "cellular" -> cellularRuns.findById(runId).filter(r -> caseId.equals(r.getDonorCaseId()))
                    .map(r -> new RunDetail(summary(r), null, json(r.getResultJson())))
                    .orElseThrow(CaseHistoryService::notFound);
            case "grading" -> gradingRuns.findById(runId).filter(r -> caseId.equals(r.getDonorCaseId()))
                    .map(r -> new RunDetail(summary(r), json(r.getClinicalFeaturesJson()), json(r.getResultJson())))
                    .orElseThrow(CaseHistoryService::notFound);
            case "disease" -> diseaseRuns.findById(runId).filter(r -> caseId.equals(r.getDonorCaseId()))
                    .map(r -> new RunDetail(summary(r), json(r.getMeasurementsJson()), json(r.getResultJson())))
                    .orElseThrow(CaseHistoryService::notFound);
            case "combined" -> combinedRuns.findById(runId).filter(r -> caseId.equals(r.getDonorCaseId()))
                    .map(r -> new RunDetail(summary(r), json(r.getClinicalFeaturesJson()), json(r.getResultJson())))
                    .orElseThrow(CaseHistoryService::notFound);
            default -> throw notFound();
        };
    }

    private RunSummary summary(CellularAnalysisRun r) {
        Map<String, Object> headline = new LinkedHashMap<>();
        headline.put("ecd", r.getEcd());
        headline.put("cv", r.getCv());
        headline.put("hex", r.getHex());
        headline.put("cellCount", r.getCellCount());
        headline.put("reliable", r.getReliable());
        return new RunSummary(r.getId(), "cellular", r.getStatus(), r.getErrorCode(), r.getImageId(),
                r.getCaseAnalysisId(), r.getCreatedAt(), headline);
    }

    private RunSummary summary(GradingAnalysisRun r) {
        Map<String, Object> headline = new LinkedHashMap<>();
        headline.put("grade", r.getGrade());
        headline.put("ecd", r.getEcd());
        return new RunSummary(r.getId(), "grading", r.getStatus(), r.getErrorCode(), r.getImageId(),
                r.getCaseAnalysisId(), r.getCreatedAt(), headline);
    }

    private RunSummary summary(DiseaseAnalysisRun r) {
        Map<String, Object> headline = new LinkedHashMap<>();
        JsonNode result = json(r.getResultJson());
        if (result != null) {
            headline.put("normal", result.path("normal").isMissingNode() ? null : result.path("normal").asBoolean());
            List<String> detected = new ArrayList<>();
            result.path("detected").forEach(d -> detected.add(d.asString()));
            headline.put("detected", detected);
            headline.put("overallSeverity", result.path("overallSeverity").isString()
                    ? result.path("overallSeverity").asString() : null);
        }
        headline.put("forced", r.isForced());
        return new RunSummary(r.getId(), "disease", r.getStatus(), r.getErrorCode(), r.getImageId(),
                r.getCaseAnalysisId(), r.getCreatedAt(), headline);
    }

    private RunSummary summary(AnalysisRun r) {
        Map<String, Object> headline = new LinkedHashMap<>();
        JsonNode result = json(r.getResultJson());
        JsonNode grade = result == null ? null : result.path("grading").path("grade");
        headline.put("grade", grade != null && grade.isString() ? grade.asString() : null);
        return new RunSummary(r.getId(), "combined", r.getStatus(), r.getErrorCode(), r.getImageId(), null,
                r.getCreatedAt(), headline);
    }

    private JsonNode json(String text) {
        return text == null ? null : objectMapper.readTree(text);
    }

    private static AnalysisRejectedException notFound() {
        return new AnalysisRejectedException(HttpStatus.NOT_FOUND, "RUN_NOT_FOUND", "runId",
                "The analysis was not found in this case.");
    }
}
