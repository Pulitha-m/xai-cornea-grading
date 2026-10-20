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
import com.cornealai.backend.analysis.service.RunArtifactService;
import com.cornealai.backend.audit.AuditService;
import tools.jackson.databind.node.ObjectNode;
import com.cornealai.backend.cases.TissueNumber;
import com.cornealai.backend.cases.dto.CaseDtos.ModuleRun;
import com.cornealai.backend.cases.dto.CaseDtos.ModuleRunPage;
import com.cornealai.backend.cases.dto.CaseDtos.RunDetail;
import com.cornealai.backend.cases.dto.CaseDtos.RunSummary;
import com.cornealai.backend.cases.entity.DonorCase;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

/** Every saved run of a donor case, across modules, newest first; and one run in full. */
@Service
public class CaseHistoryService {

    private final DonorCaseService donorCases;
    private final CellularAnalysisRunRepository cellularRuns;
    private final GradingAnalysisRunRepository gradingRuns;
    private final DiseaseAnalysisRunRepository diseaseRuns;
    private final AnalysisRunRepository combinedRuns;
    private final RunArtifactService artifacts;
    private final AuditService audit;
    private final ObjectMapper objectMapper;

    public CaseHistoryService(DonorCaseService donorCases, CellularAnalysisRunRepository cellularRuns,
                              GradingAnalysisRunRepository gradingRuns, DiseaseAnalysisRunRepository diseaseRuns,
                              AnalysisRunRepository combinedRuns, RunArtifactService artifacts, AuditService audit,
                              ObjectMapper objectMapper) {
        this.artifacts = artifacts;
        this.audit = audit;
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

    private record Row(RunSummary summary, UUID caseId) {
    }

    /**
     * Saved runs of one module across all cases (or one case, by tissue ID), newest first, for the module
     * pages. Keyset paging: pass the returned {@code nextBefore} as {@code before} for older runs. An
     * unknown tissue ID gives an empty page. Listing shows tissue IDs, so it is audited.
     */
    public ModuleRunPage moduleRuns(String module, String tissueId, Instant before, Integer limit, Long userId) {
        int size = Math.clamp(limit == null ? 20 : limit, 1, 100);
        Instant cursor = before == null ? Instant.now().plusSeconds(1) : before;
        UUID caseId = null;
        if (tissueId != null && !tissueId.isBlank()) {
            Optional<DonorCase> found = donorCases.find(TissueNumber.parse(tissueId));
            if (found.isEmpty()) {
                return new ModuleRunPage(List.of(), null);
            }
            caseId = found.get().getId();
        }
        PageRequest page = PageRequest.of(0, size + 1);  // one extra tells whether older runs exist
        UUID only = caseId;
        List<Row> rows = switch (module) {
            case "cellular" -> (only == null
                    ? cellularRuns.findByDonorCaseIdIsNotNullAndCreatedAtBeforeOrderByCreatedAtDesc(cursor, page)
                    : cellularRuns.findByDonorCaseIdAndCreatedAtBeforeOrderByCreatedAtDesc(only, cursor, page))
                    .stream().map(r -> new Row(summary(r), r.getDonorCaseId())).toList();
            case "grading" -> (only == null
                    ? gradingRuns.findByDonorCaseIdIsNotNullAndCreatedAtBeforeOrderByCreatedAtDesc(cursor, page)
                    : gradingRuns.findByDonorCaseIdAndCreatedAtBeforeOrderByCreatedAtDesc(only, cursor, page))
                    .stream().map(r -> new Row(summary(r), r.getDonorCaseId())).toList();
            case "disease" -> (only == null
                    ? diseaseRuns.findByDonorCaseIdIsNotNullAndCreatedAtBeforeOrderByCreatedAtDesc(cursor, page)
                    : diseaseRuns.findByDonorCaseIdAndCreatedAtBeforeOrderByCreatedAtDesc(only, cursor, page))
                    .stream().map(r -> new Row(summary(r), r.getDonorCaseId())).toList();
            case "combined" -> (only == null
                    ? combinedRuns.findByDonorCaseIdIsNotNullAndCreatedAtBeforeOrderByCreatedAtDesc(cursor, page)
                    : combinedRuns.findByDonorCaseIdAndCreatedAtBeforeOrderByCreatedAtDesc(only, cursor, page))
                    .stream().map(r -> new Row(summary(r), r.getDonorCaseId())).toList();
            default -> throw new AnalysisRejectedException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "module",
                    "Unknown module '" + module + "'.");
        };

        List<Row> shown = rows.subList(0, Math.min(size, rows.size()));
        Map<UUID, String> tissueIds = new HashMap<>();
        List<ModuleRun> items = shown.stream().map(row -> new ModuleRun(row.summary(), row.caseId(),
                tissueIds.computeIfAbsent(row.caseId(),
                        id -> donorCases.tissueNumberOf(donorCases.require(id)).value()))).toList();
        Instant nextBefore = rows.size() > size ? shown.getLast().summary().createdAt() : null;
        audit.record(userId, AuditService.CASE_LIST, null, only, items.size() + " " + module + " runs");
        return new ModuleRunPage(items, nextBefore);
    }

    /**
     * One run of this case as a full report: its inputs and stored result, with the result images put
     * back (decrypted) and the case shown by tissue ID. 404 when it does not exist or belongs to another case.
     */
    public RunDetail run(UUID caseId, String module, UUID runId, Long userId) {
        RunDetail stored = storedRun(caseId, module, runId);
        JsonNode result = stored.result();
        if (result instanceof ObjectNode report) {
            report.put("caseId", donorCases.tissueNumberOf(donorCases.require(caseId)).value());
            result = artifacts.restore(module, runId, report);
        }
        audit.record(userId, AuditService.RUN_VIEW, module + "_run", runId, null);
        return new RunDetail(stored.summary(), stored.inputs(), result);
    }

    private RunDetail storedRun(UUID caseId, String module, UUID runId) {
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
