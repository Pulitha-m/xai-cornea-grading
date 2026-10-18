package com.cornealai.backend.analysis.dto.disease;

/** One input-check error or warning; {@code field} is a measurement name, "image" or null. */
public record InputIssue(String code, String field, String message) {
}
