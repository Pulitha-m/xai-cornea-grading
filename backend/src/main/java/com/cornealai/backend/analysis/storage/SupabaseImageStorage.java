package com.cornealai.backend.analysis.storage;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.config.AnalysisProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

import java.util.Map;

/**
 * Supabase Storage via its REST API, authenticated with the service-role key from the
 * server environment. The key is sent only to Supabase and never logged or returned.
 * The bucket must be private; this is verified before first use.
 */
@Component
public class SupabaseImageStorage implements ImageStorage {

    private static final Logger log = LoggerFactory.getLogger(SupabaseImageStorage.class);

    private final AnalysisProperties.Storage settings;
    private final RestClient client;
    private volatile boolean bucketVerified;

    public SupabaseImageStorage(AnalysisProperties properties) {
        this.settings = properties.storage();
        if (!settings.configured()) {
            this.client = null;
            return;
        }
        String key = settings.serviceKey().trim();
        RestClient.Builder builder = RestClient.builder()
                .baseUrl(settings.supabaseUrl().trim().replaceAll("/+$", "") + "/storage/v1")
                .defaultHeader("apikey", key);
        // Legacy service_role keys are JWTs and go in the Authorization header too. New
        // secret keys (sb_secret_...) are not JWTs and must only be sent as "apikey".
        if (isJwt(key)) {
            builder.defaultHeader("Authorization", "Bearer " + key);
        } else if (!key.startsWith("sb_secret_")) {
            log.error("SUPABASE_SERVICE_ROLE_KEY is neither a service_role JWT nor an sb_secret_ key; "
                    + "check Project Settings > API Keys");
        }
        this.client = builder.build();
    }

    static boolean isJwt(String key) {
        return key.startsWith("eyJ") && key.chars().filter(c -> c == '.').count() == 2;
    }

    @Override
    public String bucket() {
        return settings.bucket();
    }

    @Override
    public void store(String objectPath, byte[] data, String contentType) {
        ensureReady();
        call("upload", () -> client.post()
                .uri("/object/{bucket}/{folder}/{file}", settings.bucket(), folder(objectPath), file(objectPath))
                .contentType(MediaType.parseMediaType(contentType))
                .header("x-upsert", "false")
                .body(data)
                .retrieve()
                .toBodilessEntity());
    }

    @Override
    public byte[] read(String objectPath) {
        ensureReady();
        return call("download", () -> client.get()
                .uri("/object/authenticated/{bucket}/{folder}/{file}", settings.bucket(), folder(objectPath), file(objectPath))
                .retrieve()
                .body(byte[].class));
    }

    @Override
    public void delete(String objectPath) {
        ensureReady();
        call("delete", () -> client.delete()
                .uri("/object/{bucket}/{folder}/{file}", settings.bucket(), folder(objectPath), file(objectPath))
                .retrieve()
                .toBodilessEntity());
    }

    /** Object paths are server-generated as "folder/file"; each part is sent as one encoded path segment. */
    private static String folder(String objectPath) {
        return objectPath.substring(0, objectPath.indexOf('/'));
    }

    private static String file(String objectPath) {
        return objectPath.substring(objectPath.indexOf('/') + 1);
    }

    private void ensureReady() {
        if (client == null) {
            throw unavailable("Image storage is not configured.");
        }
        if (!bucketVerified) {
            Map<?, ?> bucket = call("bucket check", () -> client.get()
                    .uri("/bucket/{bucket}", settings.bucket())
                    .retrieve()
                    .body(Map.class));
            if (bucket == null || !Boolean.FALSE.equals(bucket.get("public"))) {
                log.error("Supabase bucket '{}' is public or missing; refusing to use it", settings.bucket());
                throw unavailable("Image storage is not configured securely.");
            }
            bucketVerified = true;
        }
    }

    private <T> T call(String operation, java.util.function.Supplier<T> request) {
        try {
            return request.get();
        } catch (RestClientResponseException e) {
            // Supabase's error message (e.g. "Bucket not found", "Invalid Compact JWS") never contains
            // the key; the exception's own message can echo request URLs, so it is not logged.
            log.warn("Supabase storage {} failed: HTTP {} {}", operation, e.getStatusCode().value(),
                    supabaseMessage(e.getResponseBodyAsString()));
            throw unavailable("The image could not be stored or retrieved. Try again later.");
        } catch (RestClientException e) {
            log.warn("Supabase storage {} failed: {}", operation, e.getClass().getSimpleName());
            throw unavailable("The image could not be stored or retrieved. Try again later.");
        }
    }

    /** Extracts Supabase's "message" (and "error") fields; anything else is dropped. */
    static String supabaseMessage(String body) {
        java.util.regex.Matcher error = java.util.regex.Pattern.compile("\"error\"\\s*:\\s*\"([^\"]{1,100})\"").matcher(body);
        java.util.regex.Matcher message = java.util.regex.Pattern.compile("\"message\"\\s*:\\s*\"([^\"]{1,200})\"").matcher(body);
        return (error.find() ? error.group(1) + ": " : "") + (message.find() ? message.group(1) : "(no message)");
    }

    private static AnalysisRejectedException unavailable(String message) {
        return new AnalysisRejectedException(HttpStatus.BAD_GATEWAY, "IMAGE_STORAGE_ACCESS_FAILED", null, message);
    }
}
