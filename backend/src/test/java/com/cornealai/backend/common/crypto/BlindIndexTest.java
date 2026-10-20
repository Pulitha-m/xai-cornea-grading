package com.cornealai.backend.common.crypto;

import org.junit.jupiter.api.Test;

import static com.cornealai.backend.common.crypto.FieldCipherTest.key;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class BlindIndexTest {

    private static final String FIELD = "donor_cases.tissue_number";

    private final BlindIndex index = new BlindIndex(new CryptoProperties("k1", key('1'), null, key('b')));

    @Test
    void sameIdentifierSameIndexIgnoringCaseAndSurroundingWhitespace() {
        String expected = index.of(FIELD, "12656R");
        assertThat(expected).hasSize(64).matches("[0-9a-f]+");
        assertThat(index.of(FIELD, " 12656r\t")).isEqualTo(expected);
        assertThat(index.of(FIELD, "12656L")).isNotEqualTo(expected);
        assertThat(index.of(FIELD, "12657R")).isNotEqualTo(expected);
    }

    @Test
    void nothingButSurroundingWhitespaceAndCaseIsNormalised() {
        assertThat(index.of(FIELD, "1265 6R")).isNotEqualTo(index.of(FIELD, "12656R"));
        assertThat(index.of(FIELD, "012656R")).isNotEqualTo(index.of(FIELD, "12656R"));
    }

    @Test
    void fieldAndKeySeparateIndexes() {
        BlindIndex otherKey = new BlindIndex(new CryptoProperties("k1", key('1'), null, key('c')));
        assertThat(index.of("donor_cases.donor_number", "T-2023045")).isNotEqualTo(index.of(FIELD, "T-2023045"));
        assertThat(otherKey.of(FIELD, "T-2023045")).isNotEqualTo(index.of(FIELD, "T-2023045"));
    }

    @Test
    void blankIdentifierRejected() {
        assertThatThrownBy(() -> index.of(FIELD, "  ")).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void keyMustBeSetLongEnoughAndDifferentFromTheDataKey() {
        assertThatThrownBy(() -> new BlindIndex(new CryptoProperties("k1", key('1'), null, null)))
                .isInstanceOf(IllegalStateException.class).hasMessageContaining("BLIND_INDEX_KEY");
        assertThatThrownBy(() -> new BlindIndex(new CryptoProperties("k1", key('1'), null, "c2hvcnQ=")))
                .isInstanceOf(IllegalStateException.class).hasMessageContaining("256 bits");
        assertThatThrownBy(() -> new BlindIndex(new CryptoProperties("k1", key('1'), null, key('1'))))
                .isInstanceOf(IllegalStateException.class).hasMessageContaining("differ");
    }
}
