package com.cornealai.backend.analysis.dto.grading;

/**
 * The image's SHAP contribution localised over the image (base64 PNG overlays): regions that raised and
 * lowered the grade's share of votes, each scaled to its own maximum; their sizes are the totals.
 */
public record ImageAttributionMap(
        String method,
        String supportingPng,
        String opposingPng,
        Double supportingTotal,
        Double opposingTotal,
        Double localisedShare
) {

    public ImageAttributionMap withoutImages() {
        return new ImageAttributionMap(method, null, null, supportingTotal, opposingTotal, localisedShare);
    }
}
