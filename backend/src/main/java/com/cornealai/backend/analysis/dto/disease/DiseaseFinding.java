package com.cornealai.backend.analysis.dto.disease;

/**
 * One disease: model probability (not calibrated), its threshold and, if detected, the Grad-CAM
 * image and where it focuses.
 */
public record DiseaseFinding(
        String code,
        String label,
        Double probability,
        Double threshold,
        Boolean detected,
        String gradcamPng,
        GradcamFocus gradcamFocus
) {

    /** For the audit record: the focus is kept, the image is not. */
    public DiseaseFinding withoutGradcam() {
        return new DiseaseFinding(code, label, probability, threshold, detected, null, gradcamFocus);
    }
}
