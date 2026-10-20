package com.cornealai.backend.common.crypto;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class FieldCipherTest {

    private static final String KEY_1 = key('1');
    private static final String KEY_2 = key('2');
    private static final String BLIND = key('b');
    private static final String FIELD = "donor_cases.tissue_number_enc";
    private static final UUID ROW = UUID.randomUUID();

    private final FieldCipher cipher = new FieldCipher(new CryptoProperties("k1", KEY_1, null, BLIND));

    @Test
    void roundTrip() {
        for (String value : new String[]{"T-2023/045", "", "Ünïcødé – 角膜"}) {
            assertThat(cipher.decrypt(cipher.encrypt(value, FIELD, ROW), FIELD, ROW)).isEqualTo(value);
        }
    }

    @Test
    void binaryRoundTrip() {
        byte[] image = new byte[256 * 1024];
        new java.util.Random(7).nextBytes(image);
        byte[] stored = cipher.encryptBytes(image, "analysis_images.content", ROW);
        assertThat(cipher.decryptBytes(stored, "analysis_images.content", ROW)).isEqualTo(image);
        assertThatThrownBy(() -> cipher.decryptBytes(stored, "analysis_images.content", UUID.randomUUID()))
                .isInstanceOf(CryptoException.class);
    }

    @Test
    void nullStaysNull() {
        assertThat(cipher.encrypt(null, FIELD, ROW)).isNull();
        assertThat(cipher.decrypt(null, FIELD, ROW)).isNull();
    }

    @Test
    void ciphertextHidesPlaintextAndUsesAFreshIvEachTime() {
        byte[] a = cipher.encrypt("T-2023/045", FIELD, ROW);
        byte[] b = cipher.encrypt("T-2023/045", FIELD, ROW);
        assertThat(a).isNotEqualTo(b);
        assertThat(new String(a, StandardCharsets.ISO_8859_1)).doesNotContain("T-2023/045");
    }

    @Test
    void valueMovedToAnotherRowFails() {
        byte[] stored = cipher.encrypt("T-2023/045", FIELD, ROW);
        assertThatThrownBy(() -> cipher.decrypt(stored, FIELD, UUID.randomUUID()))
                .isInstanceOf(CryptoException.class);
    }

    @Test
    void valueMovedToAnotherFieldOfTheSameRowFails() {
        byte[] stored = cipher.encrypt("T-2023/045", FIELD, ROW);
        assertThatThrownBy(() -> cipher.decrypt(stored, "donor_cases.clinical_notes_enc", ROW))
                .isInstanceOf(CryptoException.class);
    }

    @Test
    void anyChangedByteFails() {
        byte[] stored = cipher.encrypt("T-2023/045", FIELD, ROW);
        for (int i = 0; i < stored.length; i++) {
            byte[] tampered = stored.clone();
            tampered[i] ^= 0x01;
            assertThatThrownBy(() -> cipher.decrypt(tampered, FIELD, ROW)).isInstanceOf(CryptoException.class);
        }
    }

    @Test
    void truncatedValueFails() {
        byte[] stored = cipher.encrypt("T-2023/045", FIELD, ROW);
        byte[] truncated = java.util.Arrays.copyOf(stored, 10);
        assertThatThrownBy(() -> cipher.decrypt(truncated, FIELD, ROW)).isInstanceOf(CryptoException.class);
    }

    @Test
    void retiredKeyStillDecryptsAndIsFlaggedForReencryption() {
        byte[] old = cipher.encrypt("T-2023/045", FIELD, ROW);
        FieldCipher rotated = new FieldCipher(new CryptoProperties("k2", KEY_2, Map.of("k1", KEY_1), BLIND));

        assertThat(rotated.decrypt(old, FIELD, ROW)).isEqualTo("T-2023/045");
        assertThat(rotated.needsReencryption(old)).isTrue();
        assertThat(rotated.needsReencryption(rotated.encrypt("x", FIELD, ROW))).isFalse();
    }

    @Test
    void unknownKeyFails() {
        byte[] stored = cipher.encrypt("T-2023/045", FIELD, ROW);
        FieldCipher other = new FieldCipher(new CryptoProperties("k2", KEY_2, null, BLIND));
        assertThatThrownBy(() -> other.decrypt(stored, FIELD, ROW))
                .isInstanceOf(CryptoException.class)
                .hasMessageNotContaining("T-2023/045");
    }

    @Test
    void missingOrWrongSizeKeyStopsStartup() {
        assertThatThrownBy(() -> new FieldCipher(new CryptoProperties("k1", "", null, BLIND)))
                .isInstanceOf(IllegalStateException.class).hasMessageContaining("DATA_ENCRYPTION_KEY");
        String shortKey = Base64.getEncoder().encodeToString(new byte[16]);
        assertThatThrownBy(() -> new FieldCipher(new CryptoProperties("k1", shortKey, null, BLIND)))
                .isInstanceOf(IllegalStateException.class).hasMessageContaining("256-bit");
        assertThatThrownBy(() -> new FieldCipher(new CryptoProperties("bad id!", KEY_1, null, BLIND)))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void rowIdAndFieldAreRequired() {
        assertThatThrownBy(() -> cipher.encrypt("x", FIELD, null)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> cipher.encrypt("x", "no_table", ROW)).isInstanceOf(IllegalArgumentException.class);
    }

    static String key(char fill) {
        return Base64.getEncoder().encodeToString(String.valueOf(fill).repeat(32).getBytes(StandardCharsets.US_ASCII));
    }
}
