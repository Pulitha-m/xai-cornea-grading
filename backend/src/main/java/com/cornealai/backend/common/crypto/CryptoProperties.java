package com.cornealai.backend.common.crypto;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.Map;

/**
 * Field-level encryption keys (application.yml: app.crypto). All keys are server-only
 * secrets: they must never be committed, logged or sent to the browser.
 *
 * @param dataKeyId       id of the key used for new encryptions; stored in every ciphertext
 * @param dataKey         base64 AES-256 key for {@code dataKeyId}
 * @param retiredDataKeys keys replaced by rotation (id to base64 key), kept only to decrypt older values
 * @param blindIndexKey   base64 HMAC key (at least 256 bits) for exact-match lookups; must differ from the data keys
 */
@ConfigurationProperties(prefix = "app.crypto")
public record CryptoProperties(
        String dataKeyId,
        String dataKey,
        Map<String, String> retiredDataKeys,
        String blindIndexKey
) {
}
