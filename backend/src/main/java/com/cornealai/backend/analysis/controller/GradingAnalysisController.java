package com.cornealai.backend.analysis.controller;

import com.cornealai.backend.analysis.dto.grading.GradingAnalyzeRequest;
import com.cornealai.backend.analysis.dto.grading.GradingAnalyzeResponse;
import com.cornealai.backend.analysis.service.GradingAnalysisService;
import com.cornealai.backend.security.AppUserDetails;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

/**
 * Donor cornea grading from the hybrid model (24 clinical features + image), with the ECD rule's
 * grade as a reference. Decision support for specialist review, not an eye-bank grading decision.
 * The image is uploaded first through POST /api/analysis/images, as for the combined analysis.
 */
@RestController
@RequestMapping("/api/analysis/grading")
public class GradingAnalysisController {

    private final GradingAnalysisService gradingAnalysisService;

    public GradingAnalysisController(GradingAnalysisService gradingAnalysisService) {
        this.gradingAnalysisService = gradingAnalysisService;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    @PreAuthorize("hasAuthority('analysis:run')")
    public GradingAnalyzeResponse analyze(
            @Valid @RequestBody GradingAnalyzeRequest request,
            @AuthenticationPrincipal AppUserDetails user
    ) {
        return gradingAnalysisService.analyze(request, user.getId());
    }
}
