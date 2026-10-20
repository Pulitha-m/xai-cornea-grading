package com.cornealai.backend.cases;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import org.springframework.http.HttpStatus;

import java.util.Locale;
import java.util.regex.Pattern;

/**
 * A donor cornea's tissue ID as users enter it: the last five digits of the tissue number followed by
 * the eye side, e.g. {@code 12656R} or {@code 12656L}. Globally unique, one per donor case.
 *
 * <p>Sensitive: it is stored only encrypted ({@code donor_cases.tissue_number_enc}) and looked up by its
 * blind index, never written to logs, other tables or the ML service. {@link #toString()} is redacted.
 */
public record TissueNumber(String value) {

    private static final Pattern FORMAT = Pattern.compile("[0-9]{5}[RL]");

    public TissueNumber {
        if (value == null || !FORMAT.matcher(value).matches()) {
            throw invalid();
        }
    }

    /** Trims surrounding whitespace and upper-cases; anything else must already match the format. */
    public static TissueNumber parse(String raw) {
        return new TissueNumber(raw == null ? null : raw.strip().toUpperCase(Locale.ROOT));
    }

    @Override
    public String toString() {
        return "TissueNumber[redacted]";
    }

    private static AnalysisRejectedException invalid() {
        return new AnalysisRejectedException(HttpStatus.BAD_REQUEST, "INVALID_TISSUE_ID", "caseId",
                "Enter the tissue ID as five digits followed by R or L, for example 12656R.");
    }
}
