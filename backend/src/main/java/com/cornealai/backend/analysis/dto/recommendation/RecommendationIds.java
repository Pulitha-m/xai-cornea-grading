package com.cornealai.backend.analysis.dto.recommendation;

/**
 * Identifiers in recommendation requests. People enter study codes (request Q0012, cornea R0012, graft G0012),
 * never real NEBSL tissue IDs, which stay encrypted in the donor cases. Corneas and grafts that come from donor
 * cases are sent by their system-generated ID instead, so the patterns also accept a UUID.
 */
final class RecommendationIds {

    static final String UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";

    private RecommendationIds() {
    }
}
