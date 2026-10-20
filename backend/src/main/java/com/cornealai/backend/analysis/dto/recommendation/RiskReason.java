package com.cornealai.backend.analysis.dto.recommendation;

/** Hazard ratio of one reason compared with the average graft (above 1 raises the risk). */
public record RiskReason(String reason, Double hazardRatio) {
}
