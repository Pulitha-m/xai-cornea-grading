package com.cornealai.backend.analysis.client;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.dto.AnalyzeResponse;
import com.cornealai.backend.analysis.dto.cellular.CellularAnalyzeResponse;
import com.cornealai.backend.analysis.dto.disease.DiseaseAnalyzeResponse;
import com.cornealai.backend.analysis.dto.disease.ImageQuality;
import com.cornealai.backend.analysis.dto.disease.InputCheck;
import com.cornealai.backend.analysis.dto.grading.GradingAnalyzeResponse;
import com.cornealai.backend.analysis.dto.recommendation.FollowupRequest;
import com.cornealai.backend.analysis.dto.recommendation.FollowupResponse;
import com.cornealai.backend.analysis.dto.recommendation.FollowupVisit;
import com.cornealai.backend.analysis.dto.recommendation.MatchRequest;
import com.cornealai.backend.analysis.dto.recommendation.MatchResponse;
import com.fasterxml.jackson.annotation.JsonInclude;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;
import tools.jackson.databind.DeserializationFeature;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.json.JsonMapper;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Sends the actual image bytes and inputs to ml-service and returns its result.
 * ml-service rejections ({"status":"rejected","error":{code,field,message}}) are
 * re-raised with the same code and message; nothing is fabricated on failure.
 */
@Component
public class MlServiceClient {

    private static final Logger log = LoggerFactory.getLogger(MlServiceClient.class);

    /** ml-service's recommendation endpoints use snake_case JSON; nulls are left out so its defaults apply. */
    private static final ObjectMapper SNAKE_CASE = JsonMapper.builder()
            .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
            .changeDefaultPropertyInclusion(incl -> incl.withValueInclusion(JsonInclude.Include.NON_NULL))
            .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
            .build();

    private final RestClient restClient;
    private final ObjectMapper objectMapper;

    public MlServiceClient(@Value("${ml.service.url}") String mlServiceUrl, ObjectMapper objectMapper) {
        this.restClient = RestClient.builder().baseUrl(mlServiceUrl).build();
        this.objectMapper = objectMapper;
    }

    /**
     * @param clinicalFeaturesJson the 24 features as a JSON object; ml-service validates them
     *                             against the training schema before any model runs
     */
    public AnalyzeResponse analyze(String caseId, String clinicalFeaturesJson, byte[] image, String filename) {
        MultiValueMap<String, Object> form = new LinkedMultiValueMap<>();
        form.add("caseId", caseId);
        form.add("clinicalFeatures", clinicalFeaturesJson);
        form.add("image", new NamedBytes(image, filename));

        try {
            return restClient.post()
                    .uri("/analyze")
                    .contentType(MediaType.MULTIPART_FORM_DATA)
                    .body(form)
                    .retrieve()
                    .body(AnalyzeResponse.class);
        } catch (RestClientResponseException e) {
            throw translate(e);
        } catch (RestClientException e) {
            log.warn("ml-service unreachable: {}", e.getClass().getSimpleName());
            throw new AnalysisRejectedException(HttpStatus.SERVICE_UNAVAILABLE, "MODEL_NOT_READY", null,
                    "The analysis service is unavailable. Try again later.");
        }
    }

    /**
     * Donor cornea grading alone (ml-service POST /grading/analyze). Rejections are raised as for analyze().
     *
     * @param clinicalFeaturesJson the 24 features as a JSON object (null = not recorded)
     */
    public GradingAnalyzeResponse analyzeGrading(String caseId, String clinicalFeaturesJson, byte[] image,
                                                 String filename) {
        MultiValueMap<String, Object> form = new LinkedMultiValueMap<>();
        form.add("caseId", caseId);
        form.add("clinicalFeatures", clinicalFeaturesJson);
        form.add("image", new NamedBytes(image, filename));

        try {
            return restClient.post()
                    .uri("/grading/analyze")
                    .contentType(MediaType.MULTIPART_FORM_DATA)
                    .body(form)
                    .retrieve()
                    .body(GradingAnalyzeResponse.class);
        } catch (RestClientResponseException e) {
            throw translate(e);
        } catch (RestClientException e) {
            log.warn("ml-service unreachable: {}", e.getClass().getSimpleName());
            throw new AnalysisRejectedException(HttpStatus.SERVICE_UNAVAILABLE, "MODEL_NOT_READY", null,
                    "The analysis service is unavailable. Try again later.");
        }
    }

    /**
     * v2 disease detection + severity (ml-service POST /disease/analyze). Failed input checks are
     * returned as a response with status "input_check_failed" carrying every error and warning, so
     * the user can correct them or force the analysis; other rejections are raised as for analyze().
     *
     * @param measurementsJson the five CellChek values as a JSON object (null = not recorded)
     */
    public DiseaseAnalyzeResponse analyzeDisease(String caseId, String measurementsJson, boolean force,
                                                 byte[] image, String filename) {
        MultiValueMap<String, Object> form = new LinkedMultiValueMap<>();
        form.add("caseId", caseId);
        form.add("measurements", measurementsJson);
        form.add("force", Boolean.toString(force));
        form.add("image", new NamedBytes(image, filename));

        try {
            return restClient.post()
                    .uri("/disease/analyze")
                    .contentType(MediaType.MULTIPART_FORM_DATA)
                    .body(form)
                    .retrieve()
                    .body(DiseaseAnalyzeResponse.class);
        } catch (RestClientResponseException e) {
            DiseaseAnalyzeResponse failedChecks = inputCheckFailure(caseId, e);
            if (failedChecks != null) {
                return failedChecks;
            }
            throw translate(e);
        } catch (RestClientException e) {
            log.warn("ml-service unreachable: {}", e.getClass().getSimpleName());
            throw new AnalysisRejectedException(HttpStatus.SERVICE_UNAVAILABLE, "MODEL_NOT_READY", null,
                    "The analysis service is unavailable. Try again later.");
        }
    }

    /**
     * Cellular analysis (ml-service POST /cellular/analyze): ROI, cells, ECD / CV / HEX. Rejections are raised as
     * for analyze().
     */
    public CellularAnalyzeResponse analyzeCellular(String caseId, byte[] image, String filename) {
        MultiValueMap<String, Object> form = new LinkedMultiValueMap<>();
        form.add("caseId", caseId);
        form.add("image", new NamedBytes(image, filename));

        try {
            return restClient.post()
                    .uri("/cellular/analyze")
                    .contentType(MediaType.MULTIPART_FORM_DATA)
                    .body(form)
                    .retrieve()
                    .body(CellularAnalyzeResponse.class);
        } catch (RestClientResponseException e) {
            throw translate(e);
        } catch (RestClientException e) {
            log.warn("ml-service unreachable: {}", e.getClass().getSimpleName());
            throw new AnalysisRejectedException(HttpStatus.SERVICE_UNAVAILABLE, "MODEL_NOT_READY", null,
                    "The analysis service is unavailable. Try again later.");
        }
    }

    /**
     * Donor-tissue ranking (ml-service POST /recommendation/match). ml-service uses snake_case JSON; the
     * backend DTOs use camelCase like the rest of the API. Rejections are raised as for analyze().
     */
    public MatchResponse recommendMatch(MatchRequest request) {
        return postRecommendation("/recommendation/match", SNAKE_CASE.writeValueAsString(request), MatchResponse.class);
    }

    /**
     * Follow-up recommendation at the 12-month visit (ml-service POST /recommendation/followup). The visit
     * fields are mapped explicitly (visit_3m, visit_6m, visit_12m). Rejections are raised as for analyze().
     */
    public FollowupResponse recommendFollowup(FollowupRequest request) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("graft_id", request.graftId());
        body.put("procedure", request.procedure());
        body.put("indication", request.indication());
        body.put("donor_age", request.donorAge());
        body.put("baseline_ecd", request.baselineEcd());
        body.put("baseline_cv", request.baselineCv());
        body.put("baseline_hex", request.baselineHex());
        body.put("visit_3m", visit(request.visit3m()));
        body.put("visit_6m", visit(request.visit6m()));
        body.put("visit_12m", visit(request.visit12m()));
        body.put("rejection_by_12m", Boolean.TRUE.equals(request.rejectionBy12m()));
        return postRecommendation("/recommendation/followup", SNAKE_CASE.writeValueAsString(body),
                FollowupResponse.class);
    }

    private static Map<String, Object> visit(FollowupVisit v) {
        if (v == null) {
            return null;
        }
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("ecd", v.ecd());
        m.put("cv", v.cv());
        m.put("hex", v.hex());
        return m;
    }

    private <T> T postRecommendation(String uri, String json, Class<T> type) {
        try {
            String response = restClient.post()
                    .uri(uri)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(json)
                    .retrieve()
                    .body(String.class);
            return SNAKE_CASE.readValue(response, type);
        } catch (RestClientResponseException e) {
            throw translate(e);
        } catch (RestClientException e) {
            log.warn("ml-service unreachable: {}", e.getClass().getSimpleName());
            throw new AnalysisRejectedException(HttpStatus.SERVICE_UNAVAILABLE, "MODEL_NOT_READY", null,
                    "The analysis service is unavailable. Try again later.");
        }
    }

    private DiseaseAnalyzeResponse inputCheckFailure(String caseId, RestClientResponseException e) {
        try {
            JsonNode body = objectMapper.readTree(e.getResponseBodyAsString());
            if (!"INPUT_CHECK_FAILED".equals(body.path("error").path("code").asString(null))
                    || !body.hasNonNull("inputCheck")) {
                return null;
            }
            return DiseaseAnalyzeResponse.inputCheckFailed(caseId,
                    body.path("error").path("message").asString(null),
                    objectMapper.treeToValue(body.get("inputCheck"), InputCheck.class),
                    body.hasNonNull("imageQuality")
                            ? objectMapper.treeToValue(body.get("imageQuality"), ImageQuality.class) : null);
        } catch (RuntimeException ignored) {
            return null; // Not a structured input-check rejection.
        }
    }

    private AnalysisRejectedException translate(RestClientResponseException e) {
        try {
            JsonNode body = objectMapper.readTree(e.getResponseBodyAsString());
            JsonNode error = body.path("error");
            if (error.hasNonNull("code") && error.hasNonNull("message")) {
                HttpStatus status = HttpStatus.resolve(e.getStatusCode().value());
                String field = error.hasNonNull("field") ? error.get("field").asString() : null;
                String message = error.get("message").asString();
                Map<String, String> fieldErrors = new LinkedHashMap<>();
                for (JsonNode item : body.path("errors")) {
                    if (item.hasNonNull("field") && item.hasNonNull("message")) {
                        fieldErrors.putIfAbsent(item.get("field").asString(), item.get("message").asString());
                    }
                }
                if (fieldErrors.isEmpty() && field != null) {
                    fieldErrors.put(field, message);
                }
                return new AnalysisRejectedException(status == null ? HttpStatus.BAD_GATEWAY : status,
                        error.get("code").asString(), field, message, fieldErrors);
            }
        } catch (RuntimeException ignored) {
            // Not a structured rejection; fall through.
        }
        log.warn("ml-service returned an unexpected {} response", e.getStatusCode().value());
        return new AnalysisRejectedException(HttpStatus.BAD_GATEWAY, "MODEL_INFERENCE_FAILED", null,
                "The analysis could not be completed. Try again later.");
    }

    /**
     * Multipart file part with a filename (required for FastAPI's UploadFile). The part's
     * content type is derived from the server-chosen extension (.jpg / .png).
     */
    private static final class NamedBytes extends ByteArrayResource {

        private final String filename;

        NamedBytes(byte[] data, String filename) {
            super(data);
            this.filename = filename;
        }

        @Override
        public String getFilename() {
            return filename;
        }
    }
}
