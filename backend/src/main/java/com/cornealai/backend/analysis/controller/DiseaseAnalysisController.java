package com.cornealai.backend.analysis.controller;

import com.cornealai.backend.analysis.dto.disease.DiseaseAnalyzeRequest;
import com.cornealai.backend.analysis.dto.disease.DiseaseAnalyzeResponse;
import com.cornealai.backend.analysis.service.DiseaseAnalysisService;
import com.cornealai.backend.security.AppUserDetails;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

/**
 * v2 corneal endothelial disease detection and severity grading (research tool, not a diagnosis).
 * The image is uploaded first through POST /api/analysis/images, as for the combined analysis.
 */
@RestController
@RequestMapping("/api/analysis/disease")
public class DiseaseAnalysisController {

    private final DiseaseAnalysisService diseaseAnalysisService;

    public DiseaseAnalysisController(DiseaseAnalysisService diseaseAnalysisService) {
        this.diseaseAnalysisService = diseaseAnalysisService;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    @PreAuthorize("hasAuthority('analysis:run')")
    public DiseaseAnalyzeResponse analyze(
            @Valid @RequestBody DiseaseAnalyzeRequest request,
            @AuthenticationPrincipal AppUserDetails user
    ) {
        return diseaseAnalysisService.analyze(request, user.getId());
    }
}
