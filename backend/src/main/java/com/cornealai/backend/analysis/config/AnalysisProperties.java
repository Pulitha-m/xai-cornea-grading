package com.cornealai.backend.analysis.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Upload limits and image storage settings (application.yml: app.analysis).
 * Image limits should match ml-service's IMAGE_* settings.
 */
@ConfigurationProperties(prefix = "app.analysis")
public record AnalysisProperties(Images images, Storage storage) {

    public record Images(long maxBytes, int minSide, int maxSide, long maxPixels) {
    }

    /**
     * Supabase Storage. {@code serviceKey} is a server-only secret: it must never be
     * exposed to the browser or logged. The bucket must be private.
     */
    public record Storage(String supabaseUrl, String serviceKey, String bucket) {

        public boolean configured() {
            return supabaseUrl != null && !supabaseUrl.isBlank()
                    && serviceKey != null && !serviceKey.isBlank()
                    && bucket != null && !bucket.isBlank();
        }
    }
}
