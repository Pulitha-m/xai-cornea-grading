package com.cornealai.backend.analysis.dto;

public record GradingResult(
        String status,
        String error,
        String grade,
        Double confidence
) {
}