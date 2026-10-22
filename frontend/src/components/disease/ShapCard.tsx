import { useState } from "react"
import { cn } from "cn"
import type { DiseaseAnalyzeResponse, ShapExplanation } from "@/api/disease"
import { MEASUREMENTS } from "@/lib/disease-measurements"
import { Card } from "@/components/dashboard/PageHeader"

/** Diverging poles (validated pair): raises = destructive red, lowers = ring blue. */
const RAISES = "bg-destructive"
const LOWERS = "bg-ring"
const LITTLE = "bg-muted-foreground/40"
/** Effects smaller than this (2 percentage points) are shown as "little effect". */
const LITTLE_EFFECT = 0.02
/** Lower bounds (percentage points / 100) of the word shown for an effect; below LITTLE_EFFECT is "little effect". */
const STRENGTHS: { min: number; word: string }[] = [
    { min: 0.25, word: "strongly" },
    { min: 0.1, word: "moderately" },
    { min: LITTLE_EFFECT, word: "slightly" },
]
/** Smallest half-width of the scale, so near-zero effects stay visibly small. */
const MIN_SCALE = 0.1

interface Target {
    id: string
    label: string
    /** What the probability is of, e.g. "FECD" or "moderate/severe Folds". */
    outcome: string
    shap: ShapExplanation
    group: "detected" | "severity" | "not-found"
}

interface Row {
    name: string
    label: string
    shown: string | null
    contribution: number
}

function targetsFrom(result: DiseaseAnalyzeResponse): Target[] {
    const diseases = result.diseases ?? []
    const out: Target[] = []
    for (const d of diseases.filter((d) => d.detected && d.shap)) {
        out.push({ id: `d-${d.code}`, label: d.label, outcome: d.label, shap: d.shap!, group: "detected" })
    }
    for (const s of (result.severity ?? []).filter((s) => s.shap)) {
        out.push({ id: `s-${s.group}`, label: `Severity: ${s.label}`, outcome: `moderate/severe ${s.label}`, shap: s.shap!, group: "severity" })
    }
    for (const d of diseases.filter((d) => !d.detected && d.shap)) {
        out.push({ id: `d-${d.code}`, label: d.label, outcome: d.label, shap: d.shap!, group: "not-found" })
    }
    return out
}

function rowsFrom(shap: ShapExplanation): Row[] {
    const byInput = new Map(shap.values.map((v) => [v.input, v]))
    return MEASUREMENTS.flatMap((m) => {
        const v = byInput.get(m.name)
        if (!v) return []
        const shown = v.imputed ? null : `${v.value!.toLocaleString("en-GB")} ${m.unit ?? ""}`.trim()
        return [{ name: m.name, label: m.label, shown, contribution: v.contribution }]
    }).sort((a, b) => Number(a.shown === null) - Number(b.shown === null) || Math.abs(b.contribution) - Math.abs(a.contribution))
}

/** "Raised strongly", "Lowered slightly", ... or "Little effect". */
function effectWords(p: number): string {
    const strength = STRENGTHS.find((s) => Math.abs(p) >= s.min)
    if (!strength) return "Little effect"
    return `${p > 0 ? "Raised" : "Lowered"} ${strength.word}`
}

function percent(p: number): string {
    return `${Math.round(p * 100)}%`
}

function joinLabels(rows: Row[]): string {
    const names = rows.map((r) => (r.shown ? `${r.label} (${r.shown})` : r.label))
    return names.length <= 1 ? names.join("") : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`
}

/** One or two plain sentences on which values drove the result. */
function summary(rows: Row[]): string {
    const recorded = rows.filter((r) => r.shown !== null)
    const raised = recorded.filter((r) => r.contribution >= LITTLE_EFFECT)
    const lowered = recorded.filter((r) => r.contribution <= -LITTLE_EFFECT)
    if (raised.length === 0 && lowered.length === 0) {
        return "The CellChek values had little effect on this result; it comes mainly from the image."
    }
    const parts: string[] = []
    if (raised.length > 0) parts.push(`Raised mainly by ${joinLabels(raised)}.`)
    if (lowered.length > 0) parts.push(`${raised.length > 0 ? "Lowered" : "Lowered mainly"} by ${joinLabels(lowered)}.`)
    return parts.join(" ")
}

/** Which CellChek values drove one disease or severity output at a time (SHAP). */
export function ShapCard({ result }: { result: DiseaseAnalyzeResponse }) {
    const targets = targetsFrom(result)
    const [selectedId, setSelectedId] = useState(targets[0]?.id ?? null)
    const selected = targets.find((t) => t.id === selectedId) ?? targets[0]
    if (!selected) return null

    const groups: { key: Target["group"]; title: string }[] = [
        { key: "detected", title: "Found" },
        { key: "severity", title: "Severity" },
        { key: "not-found", title: "Not found" },
    ]

    return (
        <Card title="Which CellChek values drove this result" description="How each value moved the model's probability. The image is the same throughout.">
            <div className="space-y-5">
                <div className="flex flex-wrap items-start gap-x-6 gap-y-3" role="group" aria-label="Choose a result to explain">
                    {groups.map(({ key, title }) => {
                        const items = targets.filter((t) => t.group === key)
                        if (items.length === 0) return null
                        return (
                            <div key={key} className="space-y-1.5">
                                <p className="text-2xs font-semibold tracking-wide text-muted-foreground uppercase">{title}</p>
                                <div className="flex flex-wrap gap-1.5">
                                    {items.map((t) => (
                                        <button
                                            key={t.id}
                                            type="button"
                                            aria-pressed={t.id === selected.id}
                                            onClick={() => setSelectedId(t.id)}
                                            className={cn(
                                                "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                                                t.id === selected.id
                                                    ? "border-secondary bg-secondary text-secondary-foreground"
                                                    : "border-border text-muted-foreground hover:bg-muted hover:text-foreground",
                                            )}
                                        >
                                            {t.label}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )
                    })}
                </div>

                <ShapChart target={selected} />

                <details className="rounded-2xl border border-border p-4 text-xs leading-relaxed text-muted-foreground">
                    <summary className="cursor-pointer font-medium text-foreground">How to read this</summary>
                    <ul className="mt-2 list-disc space-y-1 pl-5">
                        <li>
                            “Average values” means the middle (median) value of the corneas the model was trained on,
                            with this same image.
                        </li>
                        <li>
                            Each bar shows how much that value raised or lowered the probability; a longer bar means a
                            bigger effect. Strongly: 25 or more percentage points; moderately: 10–25; slightly: 2–10;
                            little effect: under 2. Together the effects add up exactly from the average-values result
                            to this result.
                        </li>
                        <li>A value that was not recorded is treated as average, so it has no effect.</li>
                        <li>
                            This shows how the model used the values, not what causes disease. ECD, SD and CV are
                            related measurements, so the model may credit one of them for what they show together
                            (for example, a high CV may appear under SD of cell area).
                        </li>
                        <li>Method: SHAP (exact Shapley values over the five values).</li>
                    </ul>
                </details>
            </div>
        </Card>
    )
}

function ShapChart({ target }: { target: Target }) {
    const { shap } = target
    const rows = rowsFrom(shap)
    const scale = Math.max(MIN_SCALE, ...rows.map((r) => Math.abs(r.contribution)))

    return (
        <div className="space-y-4">
            <div className="space-y-3 rounded-2xl bg-sunken p-4">
                <p className="text-sm">
                    Probability of <span className="font-medium">{target.outcome}</span>
                </p>
                <div className="flex flex-wrap items-baseline gap-3 tabular-nums">
                    <span className="text-sm text-muted-foreground">With average values <span className="font-semibold text-foreground">{percent(shap.baseline)}</span></span>
                    <span aria-hidden="true" className="text-muted-foreground">→</span>
                    <span className="text-sm text-muted-foreground">With these values <span className="text-lg font-semibold text-foreground">{percent(shap.prediction)}</span></span>
                </div>
                <p className="text-sm font-medium" data-testid="shap-summary">{summary(rows)}</p>
            </div>

            <table className="w-full text-sm">
                <caption className="sr-only">Effect of each CellChek value on the probability of {target.outcome}, in percentage points</caption>
                <thead className="sr-only">
                    <tr><th scope="col">Value</th><th scope="col">Effect</th><th scope="col">Change</th></tr>
                </thead>
                <tbody>
                    {rows.map((r) => {
                        const little = Math.abs(r.contribution) < LITTLE_EFFECT
                        const width = (Math.abs(r.contribution) / scale) * 50
                        const raises = r.contribution > 0
                        return (
                            <tr key={r.name} className="border-b border-muted last:border-0">
                                <th scope="row" className="w-44 py-2 pr-3 text-left align-middle font-normal">
                                    <span className="block font-medium">{r.label}</span>
                                    <span className="block text-2xs text-muted-foreground tabular-nums">{r.shown ?? "Not recorded"}</span>
                                </th>
                                <td className="py-2 align-middle">
                                    <div className="relative h-3">
                                        <div className="absolute inset-y-[-4px] left-1/2 w-px bg-border" aria-hidden="true" />
                                        {r.shown !== null && width > 0 && (
                                            <div
                                                aria-hidden="true"
                                                className={cn("absolute inset-y-0", little ? LITTLE : raises ? RAISES : LOWERS, raises ? "rounded-r" : "rounded-l")}
                                                style={raises ? { left: "50%", width: `${width}%` } : { right: "50%", width: `${width}%` }}
                                            />
                                        )}
                                    </div>
                                </td>
                                <td className="w-28 py-2 pl-3 text-right align-middle text-xs tabular-nums">
                                    {r.shown === null ? (
                                        <span className="text-muted-foreground">No effect</span>
                                    ) : (
                                        <span className={little ? "text-muted-foreground" : "font-medium"}>{effectWords(r.contribution)}</span>
                                    )}
                                </td>
                            </tr>
                        )
                    })}
                </tbody>
            </table>
        </div>
    )
}
