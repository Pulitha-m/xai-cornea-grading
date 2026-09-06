package com.cornealai.backend.analysis.client;

import com.cornealai.backend.analysis.dto.AnalyzeRequest;
import com.cornealai.backend.analysis.dto.AnalyzeResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class MlServiceClient {

    private final RestClient restClient;

    public MlServiceClient(
            @Value("${ml.service.url}") String mlServiceUrl
    ) {
        this.restClient = RestClient.builder()
                .baseUrl(mlServiceUrl)
                .build();
    }

    public AnalyzeResponse analyze(AnalyzeRequest request) {
        return restClient.post()
                .uri("/analyze")
                .body(request)
                .retrieve()
                .body(AnalyzeResponse.class);
    }
}