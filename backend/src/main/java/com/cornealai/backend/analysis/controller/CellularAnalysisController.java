package com.cornealai.backend.analysis.controller;

import com.cornealai.backend.analysis.dto.cellular.CellularAnalyzeRequest;
import com.cornealai.backend.analysis.dto.cellular.CellularAnalyzeResponse;
import com.cornealai.backend.analysis.service.CellularAnalysisService;
import com.cornealai.backend.security.AppUserDetails;
import jakarta.validation.Valid;
import org.springframework.http.MediaType;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

/**
 * Cellular analysis: automatic ROI, cell segmentation, ECD / CV / HEX with their uncertainty and per-cell
 * reliability (research tool for a specialist, not a clinical measurement).
 * The image is uploaded first through POST /api/analysis/images, as for the combined analysis.
 */
@RestController
@RequestMapping("/api/analysis/cellular")
public class CellularAnalysisController {

    private final CellularAnalysisService cellularAnalysisService;

    public CellularAnalysisController(CellularAnalysisService cellularAnalysisService) {
        this.cellularAnalysisService = cellularAnalysisService;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    @PreAuthorize("hasAuthority('analysis:run')")
    public CellularAnalyzeResponse analyze(
            @Valid @RequestBody CellularAnalyzeRequest request,
            @AuthenticationPrincipal AppUserDetails user
    ) {
        return cellularAnalysisService.analyze(request, user.getId());
    }
}
