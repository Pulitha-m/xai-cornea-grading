package com.cornealai.backend.analysis.dto;

public record AnalyzeRequest(
        String imageUrl,
        String caseId
) {
}