import type { PredictedEcd } from "@/api/recommendation"

/**
 * Plain-language reading of one graft's predicted ECD against the two clinical levels drawn on the chart:
 * below 1000 cells/mm² the graft has little reserve, below 500 it fails. Uses only the trajectory and its band
 * (no risk model), so it can be checked by eye against the chart.
 */
export const LOW_ECD = 1000
export const FAILURE_ECD = 500

export interface TrajectorySummary {
    tone: "success" | "warning" | "danger"
    text: string
}

export function trajectorySummary(ecd12m: number, predicted: PredictedEcd[]): TrajectorySummary {
    const points = [...predicted].sort((a, b) => a.months - b.months)
    const last = points[points.length - 1]
    const failing = points.find((p) => p.ecd < FAILURE_ECD)
    const low = points.find((p) => p.ecd < LOW_ECD)
    const rangeFails = points.find((p) => p.low < FAILURE_ECD)
    const range = (p: PredictedEcd) => `${p.low}–${p.high}`

    if (failing) {
        return {
            tone: "danger",
            text: `Predicted to reach the ${FAILURE_ECD} cells/mm² failure level by month ${failing.months} (${failing.ecd}).`,
        }
    }
    if (low) {
        const start = ecd12m < LOW_ECD
            ? `Already below ${LOW_ECD} cells/mm² at 12 months (${ecd12m}) and predicted to fall to ${last.ecd} by month ${last.months}.`
            : `Predicted to fall below ${LOW_ECD} cells/mm² by month ${low.months} (${low.ecd}).`
        const end = rangeFails
            ? ` The likely range at month ${rangeFails.months} (${range(rangeFails)}) could reach the ${FAILURE_ECD} failure level.`
            : ""
        return { tone: rangeFails ? "danger" : "warning", text: start + end }
    }
    const dips = last.low < LOW_ECD
        ? ` The likely range at month ${last.months} (${range(last)}) dips below ${LOW_ECD}.`
        : ""
    return {
        tone: dips ? "warning" : "success",
        text: `Predicted to stay above ${LOW_ECD} cells/mm² through month ${last.months} (${last.ecd}).${dips}`,
    }
}
