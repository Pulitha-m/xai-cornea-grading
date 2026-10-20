package com.cornealai.backend.analysis.controller;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.disease.CellChekReport;
import com.cornealai.backend.analysis.dto.disease.DiseaseAnalyzeRequest;
import com.cornealai.backend.analysis.dto.disease.DiseaseAnalyzeResponse;
import com.cornealai.backend.analysis.service.DiseaseAnalysisService;
import com.cornealai.backend.security.AppUserDetails;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;

/**
 * v2 corneal endothelial disease detection and severity grading (research tool, not a diagnosis).
 * The image is uploaded first through POST /api/analysis/images, as for the combined analysis.
 */
@RestController
@RequestMapping("/api/analysis/disease")
public class DiseaseAnalysisController {

    private final DiseaseAnalysisService diseaseAnalysisService;
    private final MlServiceClient mlServiceClient;

    public DiseaseAnalysisController(DiseaseAnalysisService diseaseAnalysisService, MlServiceClient mlServiceClient) {
        this.diseaseAnalysisService = diseaseAnalysisService;
        this.mlServiceClient = mlServiceClient;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    @PreAuthorize("hasAuthority('analysis:run')")
    public DiseaseAnalyzeResponse analyze(
            @Valid @RequestBody DiseaseAnalyzeRequest request,
            @AuthenticationPrincipal AppUserDetails user
    ) {
        return diseaseAnalysisService.analyze(request, user.getId());
    }

    /**
     * Reads ECD, SD, CV, HEX % and donor age from a CellChek report (image or .txt export) to pre-fill
     * the form. The report is passed through and never stored; it is not the model's image.
     */
    @PostMapping(path = "/report", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @PreAuthorize("hasAuthority('analysis:run')")
    public CellChekReport readReport(@RequestPart("file") MultipartFile file) {
        byte[] data;
        try {
            data = file.getBytes();
        } catch (IOException e) {
            throw new AnalysisRejectedException(HttpStatus.BAD_REQUEST, "REPORT_UNREADABLE", "file",
                    "The report could not be read. Try again.");
        }
        if (data.length == 0) {
            throw new AnalysisRejectedException(HttpStatus.UNPROCESSABLE_CONTENT, "REPORT_UNREADABLE", "file",
                    "The selected report is empty.");
        }
        String name = file.getOriginalFilename() != null && file.getOriginalFilename().toLowerCase().endsWith(".txt")
                ? "report.txt" : "report.img";
        return mlServiceClient.readCellChekReport(data, name);
    }
}
