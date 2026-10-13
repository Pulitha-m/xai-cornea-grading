package com.cornealai.backend.auth.entity;

public enum RevocationReason {
    /** Replaced by a new token during a normal refresh. */
    ROTATED,
    /** The user signed out. */
    LOGOUT,
    /** An already-rotated token was presented again; the whole session was revoked. */
    REUSE_DETECTED,
    /** The account was disabled, its role changed, or its password was reset. */
    ACCOUNT_CHANGED
}
