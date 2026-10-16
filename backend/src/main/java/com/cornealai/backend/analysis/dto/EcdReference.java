package com.cornealai.backend.analysis.dto;

import java.util.Map;

/** Grade from the ECD threshold tree alone, shown next to the hybrid model's grade. */
public record EcdReference(
        String status,
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
