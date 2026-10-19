package com.cornealai.backend.analysis.dto.cellular;

import java.util.List;

/** 95 % CIs [low, high] by block bootstrap; they cover sampling, not segmentation error. */
public record CellularUncertainty(
        String method,
        List<Double> ecdCi95,
        List<Double> cvCi95,
        List<Double> hexCi95
) {
}
