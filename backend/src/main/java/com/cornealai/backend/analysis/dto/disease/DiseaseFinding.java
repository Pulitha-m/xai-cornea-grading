package com.cornealai.backend.analysis.dto.disease;

/** One disease: model probability (not calibrated), its threshold and the Grad-CAM image if detected. */
public record DiseaseFinding(
        String code,
        String label,
        Double probability,
        Double threshold,
        Boolean detected,
        String gradcamPng
) {

    public DiseaseFinding withoutGradcam() {
        return new DiseaseFinding(code, label, probability, threshold, detected, null);
    }
}
