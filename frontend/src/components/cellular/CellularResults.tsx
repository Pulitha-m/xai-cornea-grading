import { useState } from "react"
import type { CellularAnalyzeResponse, QualityFlag } from "@/api/cellular"
import { alertError, alertWarning } from "@/lib/styles"
import { Card } from "@/components/dashboard/PageHeader"
import { Field } from "@/components/ui/field"
import { StatusBadge } from "@/components/ui/status-badge"

const sectionLabel = "text-2xs font-semibold tracking-wide text-muted-foreground uppercase"

/** Values are percentages already (e.g. 27.5), not fractions. */
function pct(value: number | null | undefined, digits = 1): string | null {
    return value === null || value === undefined ? null : `${value.toFixed(digits)}%`
}

function count(value: number | null | undefined): string | null {
    return value === null || value === undefined ? null : Math.round(value).toLocaleString("en-GB")
}

function ci(range: (number | null)[] | undefined, format: (v: number) => string): string | null {
    if (!range || range.length !== 2 || range[0] === null || range[1] === null) return null
    return `95% CI ${format(range[0])} – ${format(range[1])}`
}

const VIEWS = [
    {
        key: "overlay",
        label: "Measured cells",
        caption: "Cyan line = analysable region (outside dimmed). Measured cells coloured by side count: ≤4 purple, 5 orange, 6 green, 7 blue, ≥8 red, unknown grey.",
    },
    {
        key: "reliability",
        label: "Reliability",
        caption: "Green = no warning; yellow = low segmentation confidence; red = implausible size or shape. Check yellow and red cells first.",
    },
    {
        key: "cvEvidence",
        label: "Cell area (CV)",
        caption: "Cells coloured by area vs the median (blue = half or less, white = median, red = double or more). Yellow outline = the 5 % most extreme cells, which drive CV.",
    },
] as const

type ViewKey = (typeof VIEWS)[number]["key"]

function Flags({ flags }: { flags: QualityFlag[] }) {
    const errors = flags.filter((f) => f.level === "error")
    const warnings = flags.filter((f) => f.level !== "error")
    return (
        <>
            {errors.length > 0 && (
                <div role="alert" className={alertError}>
                    <p className="font-medium">The biomarkers are not reliable:</p>
                    <ul className="mt-1 list-disc pl-5">{errors.map((f) => <li key={f.code}>{f.message}</li>)}</ul>
                </div>
            )}
            {warnings.length > 0 && (
                <div role="alert" className={alertWarning}>
                    <p className="font-medium">Check before use:</p>
                    <ul className="mt-1 list-disc pl-5">{warnings.map((f) => <li key={f.code}>{f.message}</li>)}</ul>
                </div>
            )}
        </>
    )
}

function Biomarker({ label, value, unit, interval }: { label: string; value: string | null; unit?: string; interval: string | null }) {
    return (
        <div>
            <Field label={label} value={value} unit={unit} />
            {interval && <p className="mt-0.5 text-2xs text-muted-foreground tabular-nums">{interval}</p>}
        </div>
    )
}

/** The cellular report: ECD / CV / HEX with their uncertainty, flags, per-cell reliability and overlays. */
export function CellularResults({ result }: { result: CellularAnalyzeResponse }) {
    const [view, setView] = useState<ViewKey>("overlay")
    const b = result.biomarkers
    const u = result.uncertainty
    const rel = result.reliability
    const images = result.images
    const shown = VIEWS.find((v) => v.key === view)!
    const source = images
        ? { overlay: images.overlayJpeg, reliability: images.reliabilityJpeg, cvEvidence: images.cvEvidenceJpeg }[view]
        : null
    const sides = b.sideDistributionPct ?? {}
    const areas = b.areaPercentilesUm2 ?? {}

    return (
        <section aria-labelledby="cellular-results-title" className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 id="cellular-results-title" className="flex items-center gap-3 text-sm font-semibold">
                    Results for case <span className="font-mono">{result.caseId}</span>
                    {result.reliable
                        ? <StatusBadge tone="success">Completed</StatusBadge>
                        : <StatusBadge tone="danger">Not reliable</StatusBadge>}
                </h2>
                <p className="text-2xs text-muted-foreground">Research tool — not a clinical measurement.</p>
            </div>

            <Flags flags={result.qualityFlags ?? []} />

            <div className="grid gap-6 lg:grid-cols-2">
                <Card title="Biomarkers" description="Over all complete cells in the analysable region (cells touching its edge are not measured).">
                    <dl className="grid grid-cols-2 gap-x-4 gap-y-5 sm:grid-cols-3">
                        <Biomarker label="Endothelial cell density" value={count(b.ecd)} unit="cells/mm²"
                            interval={ci(u?.ecdCi95, (v) => Math.round(v).toLocaleString("en-GB"))} />
                        <Biomarker label="Coefficient of variation" value={pct(b.coefficientOfVariation)}
                            interval={ci(u?.cvCi95, (v) => v.toFixed(1))} />
                        <Biomarker label="Hexagonality" value={pct(b.hexagonality)}
                            interval={ci(u?.hexCi95, (v) => v.toFixed(1))} />
                        <Biomarker label="Cells measured" value={count(b.cellCount)} interval={null} />
                        <Biomarker label="Mean cell area" value={count(b.meanAreaUm2)} unit="µm²" interval={null} />
                        <Biomarker label="Cells with side count" value={count(b.cellsWithSides)} interval={null} />
                    </dl>
                    <p className="mt-4 text-xs text-muted-foreground">
                        The 95 % intervals show sampling uncertainty over the measured cells, not segmentation error.
                    </p>
                </Card>

                <Card title="Cell reliability" description="Every measured cell is rated; the rule was checked against manual cell outlines.">
                    {rel ? (
                        <div className="space-y-4">
                            <dl className="grid grid-cols-3 gap-4">
                                <Field label="Green" value={count(rel.green)} />
                                <Field label="Yellow" value={count(rel.yellow)} />
                                <Field label="Red" value={count(rel.red)} />
                            </dl>
                            <ul className="space-y-1.5 text-xs text-muted-foreground">
                                <li className="flex items-center gap-2"><StatusBadge tone="success">Green</StatusBadge> no warning</li>
                                <li className="flex items-center gap-2"><StatusBadge tone="warning">Yellow</StatusBadge> low segmentation confidence</li>
                                <li className="flex items-center gap-2"><StatusBadge tone="danger">Red</StatusBadge> implausible size or shape</li>
                            </ul>
                            <p className="text-xs text-muted-foreground">
                                Yellow and red cells are often wrong and worth checking; green cells are not guaranteed correct.
                                {rel.medianConfidence !== null && ` Median confidence ${rel.medianConfidence.toFixed(2)}.`}
                            </p>
                        </div>
                    ) : (
                        <p className="text-sm text-muted-foreground">No cells were measured.</p>
                    )}
                </Card>
            </div>

            {images && (
                <Card title="Overlays" description={shown.caption}>
                    <div role="group" aria-label="Overlay" className="mb-4 flex flex-wrap gap-2">
                        {VIEWS.filter((v) => v.key !== "reliability" || images.reliabilityJpeg).map((v) => (
                            <button
                                key={v.key}
                                type="button"
                                aria-pressed={view === v.key}
                                onClick={() => setView(v.key)}
                                className={`inline-flex h-8 items-center rounded-full border px-3.5 text-xs font-semibold transition-colors ${
                                    view === v.key ? "border-primary bg-primary text-primary-foreground" : "border-border hover:bg-sunken"
                                }`}
                            >
                                {v.label}
                            </button>
                        ))}
                    </div>
                    {source && (
                        <img
                            src={`data:image/jpeg;base64,${source}`}
                            alt={`${shown.label} overlay for case ${result.caseId}`}
                            className="w-full rounded-2xl border border-border"
                        />
                    )}
                </Card>
            )}

            <Card title="Details" description="Distributions, the analysable region and the measurement settings.">
                <div className="space-y-5">
                    <div>
                        <p className={sectionLabel}>Side count of the cells with a side count</p>
                        <dl className="mt-2 grid grid-cols-5 gap-3">
                            {["<=4", "5", "6", "7", ">=8"].map((k) => (
                                <Field key={k} label={k.replace("<=", "≤").replace(">=", "≥") + " sides"} value={pct(sides[k])} />
                            ))}
                        </dl>
                    </div>
                    <div>
                        <p className={sectionLabel}>Cell area percentiles (µm²)</p>
                        <dl className="mt-2 grid grid-cols-5 gap-3">
                            {["p5", "p25", "p50", "p75", "p95"].map((k) => (
                                <Field key={k} label={k === "p50" ? "median" : k} value={count(areas[k])} />
                            ))}
                        </dl>
                    </div>
                    <dl className="grid grid-cols-2 gap-4 border-t border-border pt-4 sm:grid-cols-4">
                        <Field label="SD of cell area" value={count(b.sdAreaUm2)} unit="µm²" />
                        <Field label="Mean compactness" value={b.meanCompactness?.toFixed(3) ?? null} />
                        <Field label="Flagged cells" value={count(b.flaggedCells)} />
                        <Field label="5 % extreme cells → CV" value={pct(result.evidence?.theirShareOfAreaVariancePct ?? null, 0)}
                            unit="of area variance" />
                        <Field label="Analysable region" value={result.roi ? pct(result.roi.shareOfLitArea * 100, 0) : null} unit="of lit area" />
                        <Field label="Region quality" value={result.roi ? result.roi.qualityScore.toFixed(2) : null} />
                        <Field label="Scale" value={result.umPerPx?.toFixed(3) ?? null} unit="µm / px" />
                        <Field label="Analysis time" value={result.seconds?.toFixed(1) ?? null} unit="s" />
                    </dl>
                </div>
            </Card>

            {result.message && <p className="text-xs text-muted-foreground">{result.message}</p>}
        </section>
    )
}
