package com.cornealai.backend.cases;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class TissueNumberTest {

    @Test
    void trimsAndUpperCases() {
        assertThat(TissueNumber.parse("12656R").value()).isEqualTo("12656R");
        assertThat(TissueNumber.parse("  12656l\t").value()).isEqualTo("12656L");
        assertThat(TissueNumber.parse("00001R").value()).isEqualTo("00001R");
    }

    @Test
    void rejectsAnythingButFiveDigitsAndAnEyeSide() {
        for (String bad : new String[]{null, "", "   ", "1265R", "126567R", "12656", "12656X", "12656RL", "R12656",
                "1265 6R", "12656 R", "NEB-2021-12656R", "CASE-001", "１２６５６R", "12656Ｒ"}) {
            assertThatThrownBy(() -> TissueNumber.parse(bad))
                    .as(String.valueOf(bad))
                    .isInstanceOfSatisfying(AnalysisRejectedException.class, e -> {
                        assertThat(e.getCode()).isEqualTo("INVALID_TISSUE_ID");
                        assertThat(e.getStatus().value()).isEqualTo(400);
                    });
        }
    }

    @Test
    void toStringDoesNotRevealTheId() {
        assertThat(TissueNumber.parse("12656R").toString()).doesNotContain("12656");
    }
}
