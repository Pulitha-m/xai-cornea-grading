package com.cornealai.backend.analysis.dto.cellular;

/** Why this CV: the share of the cell-area variance that comes from the most extreme cells. */
public record CellularEvidence(
        Double mostExtremeCellsPct,
        Double theirShareOfAreaVariancePct
) {
}
