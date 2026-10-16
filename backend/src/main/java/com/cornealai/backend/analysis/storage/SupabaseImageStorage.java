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
        this.client = settings.configured()
                ? RestClient.builder()
                    .baseUrl(settings.supabaseUrl().replaceAll("/+$", "") + "/storage/v1")
                    .defaultHeader("Authorization", "Bearer " + settings.serviceKey())
                    .defaultHeader("apikey", settings.serviceKey())
                    .build()
                : null;
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
        } catch (RestClientException e) {
            // Log the operation and exception type only: messages can echo request URLs.
            log.warn("Supabase storage {} failed: {}", operation, e.getClass().getSimpleName());
            throw unavailable("The image could not be stored or retrieved. Try again later.");
        }
    }

    private static AnalysisRejectedException unavailable(String message) {
        return new AnalysisRejectedException(HttpStatus.BAD_GATEWAY, "IMAGE_STORAGE_ACCESS_FAILED", null, message);
    }
}
