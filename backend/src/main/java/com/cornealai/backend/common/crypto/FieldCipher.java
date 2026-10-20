package com.cornealai.backend.common.crypto;

import org.springframework.stereotype.Component;

import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Pattern;

/**
 * AES-256-GCM encryption of sensitive database fields and stored images.
 *
 * <p>Stored layout: {@code version (1 byte) | keyId length (1 byte) | keyId (ASCII) | IV (12 bytes) | ciphertext + tag}.
 * Every encryption uses a fresh random IV. The associated data binds the header, the field name
 * (e.g. {@code donor_cases.tissue_number_enc}) and the row id, so a value moved to another row
 * or another field, or with a changed header, fails to decrypt.
 *
 * <p>Not a JPA {@code AttributeConverter} on purpose: a converter cannot see the row id.
 * The row id must therefore be assigned before encrypting.
 */
@Component
public class FieldCipher {

    private static final byte VERSION = 1;
    private static final int IV_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final int KEY_BYTES = 32;
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final Pattern KEY_ID = Pattern.compile("[A-Za-z0-9._-]{1,32}");
    private static final Pattern FIELD = Pattern.compile("[a-z0-9_]+\\.[a-z0-9_]+");

    private final SecureRandom random = new SecureRandom();
    private final String activeKeyId;
    private final Map<String, SecretKey> keys = new HashMap<>();

    public FieldCipher(CryptoProperties properties) {
        activeKeyId = properties.dataKeyId();
        if (activeKeyId == null || !KEY_ID.matcher(activeKeyId).matches()) {
            throw new IllegalStateException("app.crypto.data-key-id (DATA_ENCRYPTION_KEY_ID) must be 1-32 characters "
                    + "of letters, digits, '.', '_' or '-'");
        }
        keys.put(activeKeyId, aesKey(properties.dataKey(), "app.crypto.data-key (DATA_ENCRYPTION_KEY)"));
        if (properties.retiredDataKeys() != null) {
            properties.retiredDataKeys().forEach((id, key) -> {
                if (!KEY_ID.matcher(id).matches() || id.equals(activeKeyId)) {
                    throw new IllegalStateException("Invalid or duplicate retired data key id: " + id);
                }
                keys.put(id, aesKey(key, "app.crypto.retired-data-keys." + id));
            });
        }
    }

    /** Encrypts {@code plaintext} for one field of one row; {@code null} stays {@code null}. */
    public byte[] encrypt(String plaintext, String field, UUID rowId) {
        return plaintext == null ? null : encryptBytes(plaintext.getBytes(StandardCharsets.UTF_8), field, rowId);
    }

    /** Decrypts a value written by {@link #encrypt} for the same field and row; {@code null} stays {@code null}. */
    public String decrypt(byte[] stored, String field, UUID rowId) {
        return stored == null ? null : new String(decryptBytes(stored, field, rowId), StandardCharsets.UTF_8);
    }

    /** As {@link #encrypt}, for binary content such as an image; {@code null} stays {@code null}. */
    public byte[] encryptBytes(byte[] plaintext, String field, UUID rowId) {
        if (plaintext == null) {
            return null;
        }
        byte[] header = header(activeKeyId);
        byte[] iv = new byte[IV_BYTES];
        random.nextBytes(iv);
        try {
            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(Cipher.ENCRYPT_MODE, keys.get(activeKeyId), new GCMParameterSpec(TAG_BITS, iv));
            cipher.updateAAD(associatedData(header, field, rowId));
            byte[] sealed = cipher.doFinal(plaintext);

            ByteArrayOutputStream out = new ByteArrayOutputStream(header.length + IV_BYTES + sealed.length);
            out.writeBytes(header);
            out.writeBytes(iv);
            out.writeBytes(sealed);
            return out.toByteArray();
        } catch (GeneralSecurityException e) {
            throw new CryptoException("Encryption failed for " + field, e);
        }
    }

    /** Decrypts a value written by {@link #encryptBytes} for the same field and row; {@code null} stays {@code null}. */
    public byte[] decryptBytes(byte[] stored, String field, UUID rowId) {
        if (stored == null) {
            return null;
        }
        if (stored.length < 2 || stored[0] != VERSION) {
            throw new CryptoException("Unsupported encrypted value in " + field);
        }
        int headerLength = 2 + stored[1];
        if (stored[1] <= 0 || stored.length < headerLength + IV_BYTES + TAG_BITS / 8) {
            throw new CryptoException("Malformed encrypted value in " + field);
        }
        String keyId = new String(stored, 2, stored[1], StandardCharsets.US_ASCII);
        SecretKey key = keys.get(keyId);
        if (key == null) {
            throw new CryptoException("Unknown data key '" + keyId + "' for " + field);
        }
        try {
            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(Cipher.DECRYPT_MODE, key,
                    new GCMParameterSpec(TAG_BITS, stored, headerLength, IV_BYTES));
            cipher.updateAAD(associatedData(Arrays.copyOf(stored, headerLength), field, rowId));
            return cipher.doFinal(stored, headerLength + IV_BYTES, stored.length - headerLength - IV_BYTES);
        } catch (AEADBadTagException e) {
            throw new CryptoException("Encrypted value in " + field + " failed authentication", e);
        } catch (GeneralSecurityException e) {
            throw new CryptoException("Decryption failed for " + field, e);
        }
    }

    /** True when the value was encrypted with a retired key and should be re-encrypted (key rotation). */
    public boolean needsReencryption(byte[] stored) {
        if (stored == null || stored.length < 2 || stored[1] <= 0 || stored.length < 2 + stored[1]) {
            return false;
        }
        return !new String(stored, 2, stored[1], StandardCharsets.US_ASCII).equals(activeKeyId);
    }

    private static byte[] header(String keyId) {
        byte[] id = keyId.getBytes(StandardCharsets.US_ASCII);
        byte[] header = new byte[2 + id.length];
        header[0] = VERSION;
        header[1] = (byte) id.length;
        System.arraycopy(id, 0, header, 2, id.length);
        return header;
    }

    private static byte[] associatedData(byte[] header, String field, UUID rowId) {
        if (field == null || !FIELD.matcher(field).matches()) {
            throw new IllegalArgumentException("Field must be 'table.column'");
        }
        if (rowId == null) {
            throw new IllegalArgumentException("Assign the row id before encrypting or decrypting");
        }
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        out.writeBytes(header);
        out.writeBytes(("|" + field + "|" + rowId).getBytes(StandardCharsets.US_ASCII));
        return out.toByteArray();
    }

    private static SecretKey aesKey(String base64, String name) {
        byte[] raw = decodeKey(base64, name);
        if (raw.length != KEY_BYTES) {
            throw new IllegalStateException(name + " must be a base64-encoded 256-bit key: openssl rand -base64 32");
        }
        return new SecretKeySpec(raw, "AES");
    }

    static byte[] decodeKey(String base64, String name) {
        if (base64 == null || base64.isBlank()) {
            throw new IllegalStateException(name + " is not set. Generate one with: openssl rand -base64 32");
        }
        try {
            return Base64.getDecoder().decode(base64.trim());
        } catch (IllegalArgumentException e) {
            throw new IllegalStateException(name + " is not valid base64");
        }
    }
}
