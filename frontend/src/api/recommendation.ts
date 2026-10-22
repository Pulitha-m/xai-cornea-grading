import { apiRequest } from "@/lib/api-client"

/* ---------------------------------------------------------------- donor-tissue matching */

export type TissueGrade = "A+" | "A" | "B" | "C"
export type SerologyStatus = "Yes" | "No" | "Unknown"

export interface MatchRequestInfo {
    /** Study code of the recipient request, e.g. Q0012. */
    requestId: string
    requestedGrade: TissueGrade
    /** PK, DALK, DSEK, DMEK, Lamellar, Patch/Tectonic. */
    surgeryType: string | null
    urgency: "Routine" | "Emergency" | null
}

/** One cornea in stock. Unknown values are null and handled by the model. */
export interface MatchCandidate {
    /** Study code of the tissue, e.g. R0233. */
    recordId: string
    grade: TissueGrade | null
    /** cells/mm² */
    ecd: number | null
    /** % */
    cv: number | null
    /** % */
    hex: number | null
    donorAge: number | null
    deathToPreservationH: number | null
    daysInStorage: number | null
    /** "No" (positive serology) is excluded by the safety rule. */
    serologyClear: SerologyStatus | null
}

export interface MatchRequest {
    request: MatchRequestInfo
    candidates: MatchCandidate[]
    /** Number of corneas returned; null = all. */
    topK: number | null
    /** "ml" = trained ranker (default), "mcda" = rule-based baseline. */
    method: "ml" | "mcda"
}

export interface ReasonEffect {
    reason: string
    /** + pushes this cornea above the other candidates. */
    effect: number
}

export interface RankedCandidate {
    rank: number
    recordId: string
    grade: string | null
    mlScore: number | null
    /** MCDA score 0–1, shown for comparison. */
    matchScore: number
    mcdaRank: number | null
    gradeGap: number | null
    criterionScores: Record<string, number>
    reasons: string[]
    why: ReasonEffect[]
    whyText: string | null
    /** Descriptive: smallest realistic change that would make it #1. */
    counterfactual: string | null
    flags: string[]
}

export interface ExcludedCandidate {
    recordId: string
    reason: string
}

export interface MatchResponse {
    analysisId: string | null
    requestId: string
    ranked: RankedCandidate[]
    excluded: ExcludedCandidate[]
    weightsUsed: Record<string, number>
    endotheliumConsidered: boolean
    methodUsed: string
    model: string
    modelSummary: Record<string, number | string> | null
    disclaimer: string
    /** Possible but unusual values to check; they do not change the result. Absent from older runs. */
    warnings?: string[]
}

export function recommendMatch(request: MatchRequest): Promise<MatchResponse> {
    return apiRequest<MatchResponse>("/api/analysis/recommendation/match", { method: "POST", body: request })
}

/* ---------------------------------------------------------------- post-transplant follow-up */

export interface FollowupVisit {
    /** cells/mm² */
    ecd: number
    /** % */
    cv: number
    /** % */
    hex: number
}

/** A graft at its 12-month visit; the 3-month visit may be missing. */
export interface FollowupRequest {
    graftId: string
    procedure: "PK" | "DSEK" | "DMEK"
    indication: string
    donorAge: number
    baselineEcd: number
    baselineCv: number
    baselineHex: number
    visit3m: FollowupVisit | null
    visit6m: FollowupVisit
    visit12m: FollowupVisit
    rejectionBy12m: boolean
}

export type AlertLevel = "green" | "amber" | "red"

export interface PredictedEcd {
    /** Months after surgery. */
    months: number
    ecd: number
    low: number
    high: number
}

export interface RiskEstimate {
    outcome: "graft_failure" | "low_ecd"
    /** Months after this (12-month) visit. */
    withinMonths: number
    probability: number
}

export interface FollowupResponse {
    analysisId: string | null
    graftId: string
    alert: AlertLevel
    nextVisitMonths: number
    rulesFired: string[]
    /** Review prompts, not treatment instructions. */
    actions: string[]
    predictedEcd: PredictedEcd[]
    bandLevel: string
    risk: RiskEstimate[]
    reasons: {
        trajectory: { reason: string; effectPct: number }[]
        graftFailure: { reason: string; hazardRatio: number }[]
        lowEcd: { reason: string; hazardRatio: number }[]
    }
    /** Descriptive: what would change the risk. */
    counterfactuals: string[]
    /** Configured alert thresholds (placeholders until agreed with clinicians). */
    alertThresholds: Record<string, number>
    /** Evaluation numbers of the models (cross-validation). */
    modelSummary: Record<string, number | string> | null
    model: string
    modelVersion: string
    rulesVersion: string | null
    dataSource: string
    disclaimer: string
    /** Possible but unusual values to check; they do not change the result. Absent from older runs. */
    warnings?: string[]
}

export function recommendFollowup(request: FollowupRequest): Promise<FollowupResponse> {
    return apiRequest<FollowupResponse>("/api/analysis/recommendation/followup", { method: "POST", body: request })
}

/* ---------------------------------------------------------------- previous runs */

export type RecommendationKind = "match" | "followup"

/** A saved run: subjectId is the request ID (matching) or graft ID (follow-up). */
export interface RecommendationRun {
    id: string
    kind: RecommendationKind
    subjectId: string
    status: string
    errorCode: string | null
    methodUsed: string | null
    /** Matching: the cornea ranked #1. */
    topRecordId: string | null
    alert: AlertLevel | null
    nextVisitMonths: number | null
    requestedBy: string | null
    createdAt: string
}

export interface RecommendationRunPage {
    items: RecommendationRun[]
    /** Pass as `before` for older runs; null when there are none. */
    nextBefore: string | null
}

export interface RecommendationRunDetail {
    summary: RecommendationRun
    /** The request the run was given (MatchRequest or FollowupRequest). */
    inputs: unknown
    /** The stored result (MatchResponse or FollowupResponse); null if the run did not complete. */
    result: unknown
}

/** Saved runs, newest first. Users without serology access only see their own. */
export function listRecommendationRuns(
    kind: RecommendationKind,
    options: { subject?: string; before?: string; limit?: number } = {},
): Promise<RecommendationRunPage> {
    const query = new URLSearchParams({ kind })
    if (options.subject) query.set("subject", options.subject)
    if (options.before) query.set("before", options.before)
    if (options.limit) query.set("limit", String(options.limit))
    return apiRequest<RecommendationRunPage>(`/api/analysis/recommendation/runs?${query}`)
}

export function getRecommendationRun(runId: string): Promise<RecommendationRunDetail> {
    return apiRequest<RecommendationRunDetail>(`/api/analysis/recommendation/runs/${encodeURIComponent(runId)}`)
}
