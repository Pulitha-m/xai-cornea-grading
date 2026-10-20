import { apiRequest } from "@/lib/api-client"

/** One audited action: who decrypted or changed what, and when (never the sensitive value itself). */
export interface AuditEntry {
    id: string
    occurredAt: string
    userId: number
    username: string
    action: string
    subjectType: string | null
    subjectId: string | null
    detail: string | null
}

/** Administrators only (audit:read). Newest first. */
export function listAuditEvents(params: { limit?: number; subjectId?: string } = {}): Promise<AuditEntry[]> {
    const query = new URLSearchParams()
    if (params.limit) query.set("limit", String(params.limit))
    if (params.subjectId) query.set("subjectId", params.subjectId)
    const suffix = query.toString() ? `?${query}` : ""
    return apiRequest<AuditEntry[]>(`/api/audit${suffix}`)
}
