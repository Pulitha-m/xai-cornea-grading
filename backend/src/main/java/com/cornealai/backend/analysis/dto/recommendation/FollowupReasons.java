package com.cornealai.backend.analysis.dto.recommendation;

import java.util.List;

/** The strongest reasons behind the predicted trajectory and each risk. */
public record FollowupReasons(
        List<TrajectoryReason> trajectory,
        List<RiskReason> graftFailure,
        List<RiskReason> lowEcd
) {
}
