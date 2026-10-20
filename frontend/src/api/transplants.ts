import type { FollowupRequest, FollowupResponse, MatchRequestInfo, MatchResponse } from "@/api/recommendation"
import { apiRequest } from "@/lib/api-client"

/**
 * Transplant workflow on donor cases (/api/transplants): rank the signed-off corneas in stock for a
 * recipient request, allocate one (its graft), record the graft's visits and get the follow-up
 * recommendation. Corneas are sent to the model by case ID; tissue IDs are only shown here.
 */

export const PROCEDURES = ["PK", "DSEK", "DMEK"] as const
export type Procedure = (typeof PROCEDURES)[number]
export const INDICATIONS = ["Fuchs/Endothelial", "Bullous keratopathy", "Failed/Re-graft", "Other"]
export const VISIT_MONTHS = [3, 6, 12] as const

export interface CaseMatchResponse {
    /** Record IDs are case IDs. */
    match: MatchResponse
    /** Case ID -> tissue ID, for display. */
    tissueIds: Record<string, string>
    considered: number
    /** Signed-off corneas left out: already allocated, or stored too long. */
    notInStock: number
}

export interface VisitView {
    month: 3 | 6 | 12
    ecd: number
    cv: number
    hex: number
    visitDate: string | null
}

export interface FollowupSummary {
    runId: string
    status: string
    errorCode: string | null
    alert: "green" | "amber" | "red" | null
    nextVisitMonths: number | null
    createdAt: string
}

export interface Graft {
    id: string
    caseId: string
    tissueId: string
    requestId: string
    procedure: Procedure
    indication: string
    surgeryDate: string | null
    rejectionBy12m: boolean | null
    donorAge: number | null
    baselineEcd: number | null
    baselineCv: number | null
    baselineHex: number | null
    visits: VisitView[]
    /** What the follow-up recommendation still needs (empty = ready). */
    missing: string[]
    latestFollowup: FollowupSummary | null
    createdAt: string
}

export interface GraftFollowup {
    summary: FollowupSummary
    request: FollowupRequest | null
    result: FollowupResponse | null
}

export interface AllocateRequest {
    caseId: string
    requestId: string
    procedure: Procedure
    indication: string
    surgeryDate: string | null
    matchRunId: string | null
}

/** Doctors only (the candidates carry serology status). */
export function matchFromCases(request: { request: MatchRequestInfo; method: "ml" | "mcda" }): Promise<CaseMatchResponse> {
    return apiRequest<CaseMatchResponse>("/api/transplants/match", { method: "POST", body: request })
}

/** Doctors only. Creates the graft; the cornea leaves the stock. */
export function allocateGraft(request: AllocateRequest): Promise<Graft> {
    return apiRequest<Graft>("/api/transplants/grafts", { method: "POST", body: request })
}

export function listGrafts(caseId?: string): Promise<Graft[]> {
    return apiRequest<Graft[]>(`/api/transplants/grafts${caseId ? `?caseId=${encodeURIComponent(caseId)}` : ""}`)
}

export function updateGraft(graftId: string, update: { indication?: string; surgeryDate?: string; rejectionBy12m?: boolean }): Promise<Graft> {
    return apiRequest<Graft>(`/api/transplants/grafts/${encodeURIComponent(graftId)}`, { method: "PUT", body: update })
}

export function recordGraftVisit(
    graftId: string, month: 3 | 6 | 12, visit: { ecd: number; cv: number; hex: number; visitDate: string | null },
): Promise<Graft> {
    return apiRequest<Graft>(`/api/transplants/grafts/${encodeURIComponent(graftId)}/visits/${month}`, { method: "PUT", body: visit })
}

export function runGraftFollowup(graftId: string): Promise<GraftFollowup> {
    return apiRequest<GraftFollowup>(`/api/transplants/grafts/${encodeURIComponent(graftId)}/followups`, { method: "POST" })
}

export function listGraftFollowups(graftId: string): Promise<FollowupSummary[]> {
    return apiRequest<FollowupSummary[]>(`/api/transplants/grafts/${encodeURIComponent(graftId)}/followups`)
}

export function getGraftFollowup(graftId: string, runId: string): Promise<GraftFollowup> {
    return apiRequest<GraftFollowup>(
        `/api/transplants/grafts/${encodeURIComponent(graftId)}/followups/${encodeURIComponent(runId)}`,
    )
}
