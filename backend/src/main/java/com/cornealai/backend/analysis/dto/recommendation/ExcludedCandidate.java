package com.cornealai.backend.analysis.dto.recommendation;

/** A cornea that was not ranked, with the reason (e.g. positive serology). */
public record ExcludedCandidate(String recordId, String reason) {
}
