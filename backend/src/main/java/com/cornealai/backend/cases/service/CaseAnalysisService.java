package com.cornealai.backend.cases.service;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.dto.cellular.CellularAnalyzeResponse;
import com.cornealai.backend.analysis.dto.disease.DiseaseAnalyzeResponse;
import com.cornealai.backend.analysis.dto.grading.GradingAnalyzeResponse;
import com.cornealai.backend.analysis.entity.AnalysisImage;
import com.cornealai.backend.analysis.service.CellularAnalysisService;
import com.cornealai.backend.analysis.service.DiseaseAnalysisService;
import com.cornealai.backend.analysis.service.GradingAnalysisService;
import com.cornealai.backend.audit.AuditService;
import com.cornealai.backend.cases.dto.CaseDtos.CaseAnalysisRequest;
import com.cornealai.backend.cases.dto.CaseDtos.CaseAnalysisResponse;
import com.cornealai.backend.cases.dto.CaseDtos.ConsistencyFlag;
import com.cornealai.backend.cases.dto.CaseDtos.ModuleOutcome;
import com.cornealai.backend.cases.entity.CaseAnalysis;
import com.cornealai.backend.cases.entity.DonorCase;
import com.cornealai.backend.cases.repository.CaseAnalysisRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import tools.jackson.databind.ObjectMapper;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/**
 * Runs the chosen modules on one image of a donor case, with inputs from the saved case details.
 * Each module runs and records its own run (linked to one {@link CaseAnalysis}); one module failing
 * never hides another's result. Cellular output feeds no other module. Consistency flags between
 * grading and disease are shown to the reviewer and never change a result.
 */
@Service
public class CaseAnalysisService {

    /** The order the modules run and are returned in. */
    public static final List<String> MODULES = List.of("cellular", "grading", "disease");
    private static final Set<String> HIGH_GRADES = Set.of("A+", "A");
    private static final Logger log = LoggerFactory.getLogger(CaseAnalysisService.class);

    private final DonorCaseService donorCases;
    private final CaseService caseService;
    private final CaseAnalysisRepository analyses;
    private final CellularAnalysisService cellular;
    private final GradingAnalysisService grading;
    private final DiseaseAnalysisService disease;
    private final AuditService audit;
    private final ObjectMapper objectMapper;

    public CaseAnalysisService(DonorCaseService donorCases, CaseService caseService, CaseAnalysisRepository analyses,
                               CellularAnalysisService cellular, GradingAnalysisService grading,
                               DiseaseAnalysisService disease, AuditService audit, ObjectMapper objectMapper) {
        this.audit = audit;
        this.donorCases = donorCases;
        this.caseService = caseService;
        this.analyses = analyses;
        this.cellular = cellular;
        this.grading = grading;
        this.disease = disease;
        this.objectMapper = objectMapper;
    }

    public CaseAnalysisResponse analyze(UUID caseId, CaseAnalysisRequest request, Long userId) {
        for (String module : request.modules()) {
            if (!MODULES.contains(module)) {
                throw new AnalysisRejectedException(HttpStatus.BAD_REQUEST, "INVALID_REQUEST", "modules",
                        "Unknown module '" + module + "'. Choose from " + String.join(", ", MODULES) + ".");
            }
        }
        DonorCase donorCase = donorCases.require(caseId);
        AnalysisImage image = caseService.requireImage(caseId, request.imageId());
        String tissueId = donorCases.tissueNumberOf(donorCase).value();
        List<String> modules = MODULES.stream().filter(request.modules()::contains).toList();

        CaseAnalysis analysis = new CaseAnalysis();
        analysis.setId(UUID.randomUUID());
        analysis.setDonorCaseId(caseId);
        analysis.setImageId(image.getId());
        analysis.setRequestedBy(userId);
        analysis.setModules(String.join(",", modules));
        analyses.saveAndFlush(analysis);  // the module runs reference it
        audit.record(userId, AuditService.CASE_ANALYSIS, "case", caseId, String.join(",", modules));

        Map<String, ModuleOutcome> outcomes = new LinkedHashMap<>();
        GradingAnalyzeResponse graded = null;
        DiseaseAnalyzeResponse diseased = null;
        for (String module : modules) {
            ModuleOutcome outcome;
            try {
                outcome = switch (module) {
                    case "cellular" -> {
                        CellularAnalyzeResponse r = cellular.run(donorCase, image, analysis.getId(), userId);
                        yield ModuleOutcome.completed(r.withCaseId(tissueId));
                    }
                    case "grading" -> {
                        requireMeasurements(donorCase);
                        graded = grading.run(donorCase, image, caseService.gradingFeatures(donorCase),
                                analysis.getId(), userId);
                        yield ModuleOutcome.completed(graded.withCaseId(tissueId));
                    }
                    default -> {
                        requireMeasurements(donorCase);
                        diseased = disease.run(donorCase, image, caseService.diseaseMeasurements(donorCase),
                                request.force(), analysis.getId(), userId);
                        yield ModuleOutcome.completed(diseased.withCaseId(tissueId));
                    }
                };
            } catch (AnalysisRejectedException e) {
                outcome = ModuleOutcome.notRun("rejected", e.getCode(), e.getMessage());
            } catch (RuntimeException e) {
                log.error("Module {} failed in case analysis {}", module, analysis.getId(), e);
                outcome = ModuleOutcome.notRun("failed", "INTERNAL_ERROR",
                        "The " + module + " analysis could not be completed. Try again later.");
            }
            outcomes.put(module, outcome);
        }

        List<ConsistencyFlag> flags = consistency(graded, diseased);
        analysis.setConsistencyJson(objectMapper.writeValueAsString(flags));
        analyses.save(analysis);
        return new CaseAnalysisResponse(analysis.getId(), tissueId, image.getId(), outcomes, flags,
                analysis.getCreatedAt());
    }

    /** Grading and disease both need the Konan measurements; without ECD there is nothing to analyse. */
    private static void requireMeasurements(DonorCase c) {
        if (c.getEcd() == null) {
            throw new AnalysisRejectedException(HttpStatus.UNPROCESSABLE_CONTENT, "CASE_DETAILS_MISSING", "ecd",
                    "Enter the Konan measurements (at least ECD) in the case details first.");
        }
    }

    static List<ConsistencyFlag> consistency(GradingAnalyzeResponse graded, DiseaseAnalyzeResponse diseased) {
        List<ConsistencyFlag> flags = new ArrayList<>();
        if (graded != null && graded.ecdReference() != null && graded.ecdReference().grade() != null
                && !graded.ecdReference().grade().equals(graded.grade())) {
            flags.add(new ConsistencyFlag("GRADE_DIFFERS_FROM_ECD_REFERENCE",
                    "The model's grade (" + graded.grade() + ") differs from the ECD reference grade ("
                            + graded.ecdReference().grade() + ")."));
        }
        if (graded != null && diseased != null && "completed".equals(diseased.status())
                && Boolean.FALSE.equals(diseased.normal()) && diseased.detected() != null
                && !diseased.detected().isEmpty() && HIGH_GRADES.contains(graded.grade())) {
            flags.add(new ConsistencyFlag("DISEASE_WITH_HIGH_GRADE",
                    "Disease findings (" + String.join(", ", diseased.detected()) + ") with grade " + graded.grade()
                            + ": check before accepting the grade."));
        }
        return flags;
    }
}
