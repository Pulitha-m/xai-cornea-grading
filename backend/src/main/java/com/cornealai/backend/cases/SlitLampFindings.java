package com.cornealai.backend.cases;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import org.springframework.http.HttpStatus;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * The 18 slit-lamp findings of the grading model, with the values it accepts. Mirrors
 * ml-service/models/grading_feature_schema.json (group "slit_lamp_finding"); ml-service validates
 * them again at analysis time.
 */
public final class SlitLampFindings {

    /** Binary findings: 1 = present, 0 = absent. */
    public static final List<String> BINARY = List.of(
            "Stroma_Is_Clear", "Stroma_Is_Compact", "Stroma_Has_Arcus", "Stroma_Has_Edema", "Stroma_Has_Scar",
            "Epi_Has_Arcus", "Epi_Has_Defect", "Epi_Has_Exposure", "Epi_Has_Haze",
            "Endo_Has_Stress_Lines", "Endo_Has_RBC", "Endo_Has_Cell_Dropout", "Descemet_Has_Folds");

    public static final Map<String, List<String>> CATEGORIES = categories();

    private SlitLampFindings() {
    }

    /** The findings in model order, each 0/1, a category, or null (not recorded); rejects anything else. */
    public static Map<String, Object> normalise(Map<String, Object> input) {
        Map<String, Object> source = input == null ? Map.of() : input;
        for (String name : source.keySet()) {
            if (!BINARY.contains(name) && !CATEGORIES.containsKey(name)) {
                throw invalid(name, name + " is not a slit-lamp finding.");
            }
        }
        Map<String, Object> out = new LinkedHashMap<>();
        for (String name : BINARY) {
            Object value = source.get(name);
            if (value instanceof Boolean flag) {
                value = flag ? 1 : 0;
            }
            if (value != null && !(value instanceof Number n && (n.doubleValue() == 0 || n.doubleValue() == 1))) {
                throw invalid(name, name + " must be 0 or 1, or blank if not recorded.");
            }
            out.put(name, value == null ? null : ((Number) value).intValue());
        }
        CATEGORIES.forEach((name, allowed) -> {
            Object value = source.get(name);
            if (value != null && !allowed.contains(value)) {
                throw invalid(name, name + " must be one of " + String.join(", ", allowed) + ", or blank.");
            }
            out.put(name, value);
        });
        return out;
    }

    private static Map<String, List<String>> categories() {
        Map<String, List<String>> map = new LinkedHashMap<>();
        map.put("Descemet_Fold_Severity", List.of("Mild", "Moderate", "Unspecified", "Very mild"));
        map.put("Descemet_Fold_Relative_Number", List.of("Mild", "Moderate", "Several", "Several/Moderate", "Unspecified"));
        map.put("Endo_Stress_Line_Location", List.of("Central", "Central + Peripheral", "Peripheral", "Unspecified"));
        map.put("Stroma_Arcus_Severity", List.of("Mild", "Moderate", "Unspecified"));
        map.put("Epi_Exposure_Severity", List.of("Mild", "Unspecified", "Very mild"));
        return java.util.Collections.unmodifiableMap(map);  // keeps the model's order
    }

    private static AnalysisRejectedException invalid(String field, String message) {
        return new AnalysisRejectedException(HttpStatus.BAD_REQUEST, "INVALID_CASE_DETAILS", field, message);
    }
}
