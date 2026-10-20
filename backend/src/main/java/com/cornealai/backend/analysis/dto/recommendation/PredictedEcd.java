package com.cornealai.backend.analysis.dto.recommendation;

/** Predicted ECD (cells/mm²) at a month after surgery, with the lower / upper end of its band. */
public record PredictedEcd(Integer months, Integer ecd, Integer low, Integer high) {
}
