package com.cornealai.backend.analysis.dto.disease;

import java.util.List;
import java.util.Map;

/**
 * CellChek values read from a report (image via OCR, or the .txt export) to pre-fill the disease
 * form. {@code values} holds the five measurements by name (null = not found); the clinician checks
 * them. {@code warnings} flag misreads (cross-checks) and values that could not be trusted.
 */
public record CellChekReport(
        String source,
        Map<String, Double> values,
        List<String> notFound,
        String tissueId,
        String eye,
        Double totalCells,
        Double totalAreaUm2,
        List<InputIssue> warnings
) {
}
