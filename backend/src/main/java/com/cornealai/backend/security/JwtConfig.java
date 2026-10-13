package com.cornealai.backend.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.*;

import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;
import java.util.Base64;
import java.util.List;

@Configuration
public class JwtConfig {

    private static final int MIN_SECRET_BYTES = 32;

    private final SecretKey secretKey;
    private final SecurityProperties.Jwt jwtProperties;

    public JwtConfig(SecurityProperties securityProperties) {
        this.jwtProperties = securityProperties.jwt();
        this.secretKey = toSecretKey(jwtProperties.secret());
    }

    @Bean
    public JwtEncoder jwtEncoder() {
        return NimbusJwtEncoder.withSecretKey(secretKey)
                .algorithm(MacAlgorithm.HS256)
                .build();
    }

    @Bean
    public JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder.withSecretKey(secretKey)
                .macAlgorithm(MacAlgorithm.HS256)
                .build();

        // Signature and algorithm are verified by the decoder; these check exp/nbf, issuer and audience.
        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(jwtProperties.issuer()),
                new JwtClaimValidator<List<String>>(
                        JwtClaimNames.AUD,
                        aud -> aud != null && aud.contains(jwtProperties.audience())
                )
        ));
        return decoder;
    }

    private static SecretKey toSecretKey(String secret) {
        if (secret == null || secret.isBlank()) {
            throw new IllegalStateException("JWT_SECRET is not configured");
        }

        byte[] keyBytes;
        try {
            keyBytes = Base64.getDecoder().decode(secret.trim());
        } catch (IllegalArgumentException e) {
            throw new IllegalStateException("JWT_SECRET must be base64-encoded (e.g. openssl rand -base64 48)");
        }

        if (keyBytes.length < MIN_SECRET_BYTES) {
            throw new IllegalStateException("JWT_SECRET must decode to at least 256 bits");
        }

        return new SecretKeySpec(keyBytes, "HmacSHA256");
    }
}
