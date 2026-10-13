package com.cornealai.backend.analysis.controller;

import com.cornealai.backend.analysis.dto.AnalyzeRequest;
import com.cornealai.backend.analysis.dto.AnalyzeResponse;
import com.cornealai.backend.analysis.service.AnalysisService;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/analysis")
public class AnalysisController {

    private final AnalysisService analysisService;

    public AnalysisController(AnalysisService analysisService) {
        this.analysisService = analysisService;
    }

    @PostMapping
    @PreAuthorize("hasAuthority('analysis:run')")
    public AnalyzeResponse analyze(@RequestBody AnalyzeRequest request) {
        return analysisService.analyze(request);
    }
}