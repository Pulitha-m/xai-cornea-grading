package com.cornealai.backend.analysis.dto.recommendation;

/** Probability of "graft_failure" or "low_ecd" (ECD below 1000) within a number of months after this visit. */
public record RiskEstimate(String outcome, Integer withinMonths, Double probability) {
}
