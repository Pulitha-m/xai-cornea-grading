import { useState } from "react"
import { cn } from "cn"
import type { DiseaseAnalyzeResponse, ShapExplanation } from "@/api/disease"
import { MEASUREMENTS } from "@/lib/disease-measurements"
import { Card } from "@/components/dashboard/PageHeader"

/** Diverging poles (validated pair): raises = destructive red, lowers = ring blue. */
const RAISES = "bg-destructive"
const LOWERS = "bg-ring"
/** Smallest half-width of the scale, so near-zero effects stay visibly small. */
const MIN_SCALE = 0.1

interface Target {
    id: string
    label: string
    /** What the probability is of, e.g. "FECD" or "Mod/Sev (Folds)". */
    outcome: string
    shap: ShapExplanation
    group: "detected" | "severity" | "not-found"
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

function points(p: number): string {
    const value = Math.round(p * 100)
    if (value === 0) return p === 0 ? "0" : p > 0 ? "+<1" : "−<1"
    return value > 0 ? `+${value}` : `−${Math.abs(value)}`
}

function percent(p: number): string {
    return `${Math.round(p * 100)}%`
}

/** SHAP values of the five CellChek values for one disease or severity output at a time. */
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
        <Card title="How the CellChek values affected the result (SHAP)">
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

                <ul className="list-disc space-y-1 pl-5 text-xs leading-relaxed text-muted-foreground">
                    <li>
                        Each bar is how much that value moved the probability, in percentage points, compared with a
                        typical training cornea (all five values at the training median). The image is kept the same.
                    </li>
                    <li>A value that was not recorded used the median, so it has no effect.</li>
                    <li>
                        This shows what the model did, not what causes disease. SD, CV and ECD are linked
                        (SD ≈ CV × mean cell area), so credit can shift between them.
                    </li>
                </ul>
            </div>
        </Card>
    )
}

function ShapChart({ target }: { target: Target }) {
    const { shap } = target
    const byInput = new Map(shap.values.map((v) => [v.input, v]))
    const scale = Math.max(MIN_SCALE, ...shap.values.map((v) => Math.abs(v.contribution)))

    return (
        <div className="space-y-3">
            <p className="text-sm">
                Probability of <span className="font-medium">{target.outcome}</span>: this image with typical values{" "}
                <span className="font-semibold tabular-nums">{percent(shap.baseline)}</span>
                <span aria-hidden="true"> → </span>
                <span className="sr-only"> changed to </span>
                with the values entered <span className="font-semibold tabular-nums">{percent(shap.prediction)}</span>
            </p>

            <div className="flex flex-wrap gap-4 text-2xs text-muted-foreground" aria-hidden="true">
                <span className="flex items-center gap-1.5"><span className={cn("size-2.5 rounded-sm", RAISES)} />Raised the probability</span>
                <span className="flex items-center gap-1.5"><span className={cn("size-2.5 rounded-sm", LOWERS)} />Lowered the probability</span>
            </div>

            <table className="w-full text-sm">
                <caption className="sr-only">Effect of each CellChek value on the probability of {target.outcome}, in percentage points</caption>
                <thead className="sr-only">
                    <tr><th scope="col">Value</th><th scope="col">Effect</th><th scope="col">Change (points)</th></tr>
                </thead>
                <tbody>
                    {MEASUREMENTS.map((m) => {
                        const v = byInput.get(m.name)
                        if (!v) return null
                        const width = (Math.abs(v.contribution) / scale) * 50
                        const raises = v.contribution > 0
                        return (
                            <tr key={m.name} className="border-b border-muted last:border-0">
                                <th scope="row" className="w-44 py-2 pr-3 text-left align-middle font-normal">
                                    <span className="block font-medium">{m.label}</span>
                                    <span className="block text-2xs text-muted-foreground tabular-nums">
                                        {v.imputed ? "not recorded (median used)" : `${v.value!.toLocaleString("en-GB")} ${m.unit ?? ""}`}
                                    </span>
                                </th>
                                <td className="py-2 align-middle">
                                    <div className="relative h-3" title={`${m.label}: ${points(v.contribution)} percentage points`}>
                                        <div className="absolute inset-y-[-4px] left-1/2 w-px bg-border" aria-hidden="true" />
                                        {width > 0 && (
                                            <div
                                                aria-hidden="true"
                                                className={cn("absolute inset-y-0", raises ? `${RAISES} rounded-r` : `${LOWERS} rounded-l`)}
                                                style={raises ? { left: "50%", width: `${width}%` } : { right: "50%", width: `${width}%` }}
                                            />
                                        )}
                                    </div>
                                </td>
                                <td className="w-16 py-2 pl-3 text-right align-middle text-xs tabular-nums">
                                    {v.imputed ? "—" : points(v.contribution)}
                                </td>
                            </tr>
                        )
                    })}
                </tbody>
            </table>
        </div>
    )
}
