package com.cornealai.backend.analysis;

import com.cornealai.backend.analysis.config.AnalysisProperties;
import com.cornealai.backend.analysis.storage.SupabaseImageStorage;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/** Header handling and safety checks against a local stand-in for the Supabase Storage API. */
class SupabaseImageStorageTest {

    private static final String JWT_KEY = "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.signature";
    private static final String SECRET_KEY = "sb_secret_example";

    private HttpServer server;
    private final Map<String, String> lastHeaders = new ConcurrentHashMap<>();

    @AfterEach
    void stop() {
        if (server != null) {
            server.stop(0);
        }
    }

    private SupabaseImageStorage storage(String key, int bucketStatus, String bucketBody) throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/storage/v1/", exchange -> {
            lastHeaders.clear();
            exchange.getRequestHeaders().forEach((name, values) -> lastHeaders.put(name.toLowerCase(), values.getFirst()));
            exchange.getRequestBody().readAllBytes();
            boolean bucketCheck = exchange.getRequestURI().getPath().startsWith("/storage/v1/bucket/");
            byte[] body = (bucketCheck ? bucketBody : "{\"Key\":\"ok\"}").getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(bucketCheck ? bucketStatus : 200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        });
        server.start();
        String url = "http://127.0.0.1:" + server.getAddress().getPort();
        return new SupabaseImageStorage(new AnalysisProperties(
                new AnalysisProperties.Images(1, 1, 1, 1),
                new AnalysisProperties.Storage(url, key, "specular-images")));
    }

    @Test
    void legacyJwtKeyIsSentAsApikeyAndBearer() throws Exception {
        storage(JWT_KEY, 200, "{\"id\":\"specular-images\",\"public\":false}").store("CASE-1/a.jpg", new byte[]{1}, "image/jpeg");
        assertThat(lastHeaders).containsEntry("apikey", JWT_KEY).containsEntry("authorization", "Bearer " + JWT_KEY);
    }

    @Test
    void newSecretKeyIsSentOnlyAsApikey() throws Exception {
        storage(SECRET_KEY, 200, "{\"id\":\"specular-images\",\"public\":false}").store("CASE-1/a.jpg", new byte[]{1}, "image/jpeg");
        assertThat(lastHeaders).containsEntry("apikey", SECRET_KEY).doesNotContainKey("authorization");
    }

    @Test
    void publicBucketIsRefused() throws Exception {
        SupabaseImageStorage storage = storage(SECRET_KEY, 200, "{\"id\":\"specular-images\",\"public\":true}");
        assertThatThrownBy(() -> storage.store("CASE-1/a.jpg", new byte[]{1}, "image/jpeg"))
                .isInstanceOfSatisfying(AnalysisRejectedException.class,
                        e -> assertThat(e.getCode()).isEqualTo("IMAGE_STORAGE_ACCESS_FAILED"));
    }

    @Test
    void rejectedKeyIsReportedAsStorageFailure() throws Exception {
        SupabaseImageStorage storage = storage("not-a-supabase-key", 400,
                "{\"statusCode\":\"403\",\"error\":\"Unauthorized\",\"message\":\"Invalid Compact JWS\"}");
        assertThatThrownBy(() -> storage.store("CASE-1/a.jpg", new byte[]{1}, "image/jpeg"))
                .isInstanceOfSatisfying(AnalysisRejectedException.class,
                        e -> assertThat(e.getCode()).isEqualTo("IMAGE_STORAGE_ACCESS_FAILED"));
    }
}
