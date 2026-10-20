package com.cornealai.backend.common.crypto;

/**
 * An encrypted value could not be decrypted (wrong key, wrong row or field, or tampered bytes).
 * The message never contains plaintext or key material.
 */
public class CryptoException extends RuntimeException {

    public CryptoException(String message) {
        super(message);
    }

    public CryptoException(String message, Throwable cause) {
        super(message, cause);
    }
}
