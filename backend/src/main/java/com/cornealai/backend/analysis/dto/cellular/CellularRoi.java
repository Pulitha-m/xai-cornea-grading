package com.cornealai.backend.analysis.dto.cellular;

/** The automatically selected analysable region (ROI) inside the illuminated area. */
public record CellularRoi(
        String method,
        Double shareOfImage,
        Double shareOfLitArea,
        Double qualityScore
) {
}
