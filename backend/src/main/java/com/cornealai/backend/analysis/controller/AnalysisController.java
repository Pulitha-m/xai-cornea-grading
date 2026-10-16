package com.cornealai.backend.analysis.controller;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.dto.AnalyzeRequest;
import com.cornealai.backend.analysis.dto.AnalyzeResponse;
import com.cornealai.backend.analysis.dto.ImageUploadResponse;
import com.cornealai.backend.analysis.service.AnalysisService;
import com.cornealai.backend.analysis.service.ImageService;
import com.cornealai.backend.security.AppUserDetails;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;

@RestController
@RequestMapping("/api/analysis")
public class AnalysisController {

    private final AnalysisService analysisService;
    private final ImageService imageService;

    public AnalysisController(AnalysisService analysisService, ImageService imageService) {
        this.analysisService = analysisService;
        this.imageService = imageService;
    }

    /** Uploads a specular microscopy image for a case; returns an id to analyse it with. */
    @PostMapping(path = "/images", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @PreAuthorize("hasAuthority('analysis:run')")
    public ResponseEntity<ImageUploadResponse> uploadImage(
            @RequestParam("caseId") String caseId,
            @RequestPart("file") MultipartFile file,
            @AuthenticationPrincipal AppUserDetails user
    ) {
        byte[] data;
        try {
            data = file.getBytes();
        } catch (IOException e) {
            throw new AnalysisRejectedException(HttpStatus.BAD_REQUEST, "IMAGE_DECODE_FAILED", "file",
                    "The upload could not be read. Try again.");
        }
        return ResponseEntity.status(HttpStatus.CREATED).body(imageService.upload(caseId, data, user.getId()));
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    @PreAuthorize("hasAuthority('analysis:run')")
    public AnalyzeResponse analyze(
            @Valid @RequestBody AnalyzeRequest request,
            @AuthenticationPrincipal AppUserDetails user
    ) {
        return analysisService.analyze(request, user.getId());
    }
}
