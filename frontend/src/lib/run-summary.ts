import type { RunSummary } from "@/api/cases"
import type { StatusTone } from "@/components/ui/status-badge"

/** Badge tone for a saved run's status. */
export const STATUS_TONES: Record<string, StatusTone> = {
    completed: "success",
    partial: "warning",
    input_check_failed: "warning",
    rejected: "danger",
    failed: "danger",
}

/** The main values of a saved run, for history lists. */
export function runHeadline(run: RunSummary): string {
    const h = run.headline
    const number = (v: unknown, digits = 0) => (typeof v === "number" ? v.toLocaleString("en-GB", { maximumFractionDigits: digits }) : "—")
    switch (run.module) {
        case "grading":
        case "combined":
            return h.grade ? `Grade ${String(h.grade)}` : "—"
        case "cellular":
            return `ECD ${number(h.ecd)} · CV ${number(h.cv, 1)} % · HEX ${number(h.hex, 1)} %${h.reliable === false ? " · not reliable" : ""}`
        case "disease": {
            const detected = Array.isArray(h.detected) ? (h.detected as string[]) : []
            if (h.normal === true) return "No disease detected"
            return detected.length > 0 ? `Detected: ${detected.join(", ")}` : "—"
        }
    }
}
