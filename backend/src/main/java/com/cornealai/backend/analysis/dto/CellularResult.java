package com.cornealai.backend.analysis.dto;

public record CellularResult(
        String status,
        String error,
        Integer cellCount,
        Double ecd,
        Double coefficientOfVariation,
        Double hexagonality
) {
}