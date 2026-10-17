package com.cornealai.backend.analysis.dto.disease;

import java.util.List;

/** Results of the input checks; {@code forced} = they failed and the analysis was run anyway. */
public record InputCheck(Boolean passed, Boolean forced, List<InputIssue> errors, List<InputIssue> warnings) {
}
