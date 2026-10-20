package com.cornealai.backend.analysis.dto.cellular;

/** Base64 JPEG overlays of the analysed image; returned to the user, not stored. */
public record CellularImages(
        String overlayJpeg,
        String reliabilityJpeg,
        String cvEvidenceJpeg
) {
}
