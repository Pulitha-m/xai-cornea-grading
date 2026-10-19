package com.cornealai.backend.analysis.dto.cellular;

import java.util.Map;

/**
 * Biomarkers over all complete cells (not touching the image border or the unanalysable area), at the calibrated
 * scale. ecd in cells/mm²; areas in µm²; coefficientOfVariation, hexagonality and cvCompactness in %.
 */
public record CellularBiomarkers(
        Integer cellCount,
        Double ecd,
        Double meanAreaUm2,
        Double sdAreaUm2,
        Double coefficientOfVariation,
        Double hexagonality,
        Integer cellsWithSides,
        Double meanCompactness,
        Double sdCompactness,
        Double cvCompactness,
        Map<String, Double> areaPercentilesUm2,
        Map<String, Double> sideDistributionPct,
        Integer flaggedCells
) {
}
