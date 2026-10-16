package com.cornealai.backend.analysis.dto;

import java.util.Map;

public record GradingResult(
        String status,
        String error,
        String grade,
        String method,
        Double ecdUsed,
        EcdBand ecdBand,
        Map<String, Double> bandDistribution,
        Integer bandTrainingTissues,
        Boolean reviewRequired,
        String message
) {
}
