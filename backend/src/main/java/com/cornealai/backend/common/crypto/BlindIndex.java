package com.cornealai.backend.common.crypto;

import org.springframework.stereotype.Component;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Locale;

/**
 * Keyed HMAC-SHA256 index for exact-match lookups on an encrypted identifier (e.g. a tissue number),
 * without storing or querying the identifier itself. A plain hash is not used: tissue numbers are
 * predictable, so an unkeyed hash could be reversed by trying them all.
 *
 * <p>The field name is part of the HMAC input, so the same value indexed for two fields gives
 * unrelated indexes.
 */
@Component
public class BlindIndex {

    private static final int MIN_KEY_BYTES = 32;
    private static final String ALGORITHM = "HmacSHA256";

    private final SecretKeySpec key;

    public BlindIndex(CryptoProperties properties) {
        byte[] raw = FieldCipher.decodeKey(properties.blindIndexKey(), "app.crypto.blind-index-key (BLIND_INDEX_KEY)");
        if (raw.length < MIN_KEY_BYTES) {
            throw new IllegalStateException("app.crypto.blind-index-key (BLIND_INDEX_KEY) must be at least 256 bits: "
                    + "openssl rand -base64 32");
        }
        if (properties.dataKey() != null && !properties.dataKey().isBlank()
                && MessageDigest.isEqual(raw, FieldCipher.decodeKey(properties.dataKey(), "app.crypto.data-key"))) {
            throw new IllegalStateException("BLIND_INDEX_KEY must differ from DATA_ENCRYPTION_KEY");
        }
        key = new SecretKeySpec(raw, ALGORITHM);
    }

    /** 64-character lowercase hex index of the normalised {@code value} for {@code field}. */
    public String of(String field, String value) {
        try {
            Mac mac = Mac.getInstance(ALGORITHM);
            mac.init(key);
            byte[] digest = mac.doFinal((field + "|" + normalize(value)).getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (GeneralSecurityException e) {
            throw new CryptoException("Blind index failed for " + field, e);
        }
    }

    /**
     * Surrounding whitespace and case are ignored (" 12656r " and "12656R" match); nothing else is changed.
     * Format checks belong to the caller (e.g. {@link com.cornealai.backend.cases.TissueNumber}).
     */
    static String normalize(String value) {
        String normalized = value == null ? "" : value.strip().toUpperCase(Locale.ROOT);
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("Identifier is blank");
        }
        return normalized;
    }
}
