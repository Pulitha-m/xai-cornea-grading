import type { StatusTone } from "@/components/ui/status-badge"

/** Display label and tone for a module's status string from the ML service. */
export function moduleStatus(status: string): { label: string; tone: StatusTone } {
    switch (status.toLowerCase()) {
        case "completed":
            return { label: "Completed", tone: "success" }
        case "failed":
            return { label: "Failed", tone: "danger" }
        case "review_required":
            return { label: "Manual grading required", tone: "warning" }
        case "partial":
            return { label: "Partially completed", tone: "info" }
        case "not_implemented":
            return { label: "Not available yet", tone: "neutral" }
        default:
            return { label: humanize(status), tone: "neutral" }
    }
}

export function isFailed(status: string): boolean {
    return status.toLowerCase() === "failed"
}

export function isNotImplemented(status: string): boolean {
    return status.toLowerCase() === "not_implemented"
}

const GRADE_ORDER = ["A+", "A", "B"]

/** Grades in display order, followed by any the UI does not know. */
export function orderedGrades(shares: Record<string, number>): string[] {
    return [...GRADE_ORDER.filter((g) => g in shares), ...Object.keys(shares).filter((g) => !GRADE_ORDER.includes(g))]
}

/** "none_detected" -> "None detected". */
export function humanize(value: string): string {
    const text = value.replace(/[_-]+/g, " ").trim().toLowerCase()
    return text.charAt(0).toUpperCase() + text.slice(1)
}

/** The ML service reports CV, hexagonality and confidence as fractions in [0, 1]. */
export function formatPercent(fraction: number | null): string | null {
    return fraction === null ? null : `${Math.round(fraction * 100)}%`
}

export function formatCount(value: number | null): string | null {
    return value === null ? null : Math.round(value).toLocaleString("en-GB")
}
