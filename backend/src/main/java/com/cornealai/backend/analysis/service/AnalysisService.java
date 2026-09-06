package com.cornealai.backend.analysis.service;

import com.cornealai.backend.analysis.client.MlServiceClient;
import com.cornealai.backend.analysis.dto.AnalyzeRequest;
import com.cornealai.backend.analysis.dto.AnalyzeResponse;
import org.springframework.stereotype.Service;

@Service
public class AnalysisService {

    private final MlServiceClient mlServiceClient;

    public AnalysisService(MlServiceClient mlServiceClient) {
        this.mlServiceClient = mlServiceClient;
    }

    public AnalyzeResponse analyze(AnalyzeRequest request) {
        return mlServiceClient.analyze(request);
    }
}