package com.cornealai.backend.analysis.dto.recommendation;

/** Effect of one reason on a cornea's score compared with the other candidates (+ pushes it up). */
public record ReasonEffect(String reason, Double effect) {
}
