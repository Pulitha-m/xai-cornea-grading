package com.cornealai.backend.analysis.dto;

/** A feature value that is accepted but unusual (e.g. outside the training range). */
public record FeatureWarning(String code, String field, String message) {
}
