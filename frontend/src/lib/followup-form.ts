import type { FollowupRequest, FollowupVisit } from "@/api/recommendation"

/** Form helpers for the post-transplant follow-up page (kept out of the component file). */
export const VISITS = [3, 6, 12] as const
export const MEASURES = [
    { key: "ecd", label: "ECD", unit: "cells/mm²" },
    { key: "cv", label: "CV", unit: "%" },
    { key: "hex", label: "HEX", unit: "%" },
] as const

export type VisitKey = `${(typeof MEASURES)[number]["key"]}${(typeof VISITS)[number]}`
export type FollowupValues = Record<"graftId" | "donorAge" | "baselineEcd" | "baselineCv" | "baselineHex" | VisitKey, string>

export const EMPTY_FOLLOWUP: FollowupValues = {
    graftId: "", donorAge: "", baselineEcd: "", baselineCv: "", baselineHex: "",
    ecd3: "", cv3: "", hex3: "", ecd6: "", cv6: "", hex6: "", ecd12: "", cv12: "", hex12: "",
}

function num(v: string): number | null {
    const t = v.trim()
    if (t === "") return null
    const n = Number(t)
    return Number.isFinite(n) ? n : null
}

/** Builds the request, or lists what is missing. The 3-month visit may be left empty (missed visit). */
export function toFollowupRequest(
    v: FollowupValues, procedure: FollowupRequest["procedure"], indication: string, rejection: boolean,
): { request: FollowupRequest | null; missing: string[] } {
    const missing: string[] = []
    const need = (key: keyof FollowupValues, label: string) => {
        const n = num(v[key])
        if (n === null) missing.push(label)
        return n ?? 0
    }
    const visit = (m: 3 | 6 | 12, optional: boolean): FollowupVisit | null => {
        const values = MEASURES.map((x) => num(v[`${x.key}${m}` as VisitKey]))
        if (optional && values.every((x) => x === null)) return null
        values.forEach((x, i) => {
            if (x === null) missing.push(`${m}-month ${MEASURES[i].label}`)
        })
        return { ecd: values[0] ?? 0, cv: values[1] ?? 0, hex: values[2] ?? 0 }
    }
    if (!v.graftId.trim()) missing.push("Graft ID")
    const request: FollowupRequest = {
        graftId: v.graftId.trim(),
        procedure,
        indication,
        donorAge: need("donorAge", "Donor age"),
        baselineEcd: need("baselineEcd", "Donor ECD"),
        baselineCv: need("baselineCv", "Donor CV"),
        baselineHex: need("baselineHex", "Donor HEX"),
        visit3m: visit(3, true),
        visit6m: visit(6, false)!,
        visit12m: visit(12, false)!,
        rejectionBy12m: rejection,
    }
    return { request: missing.length ? null : request, missing }
}
