import { useState } from "react"
import type { DiseaseAnalyzeResponse, DiseaseFinding, ImageQuality, InputIssue } from "@/api/disease"
import { measurementLabel } from "@/lib/disease-measurements"
import { coverageLabel, GRADCAM_EXPLANATIONS, regionCell } from "@/lib/gradcam-explanations"
import { alertError, alertWarning } from "@/lib/styles"
import { Card } from "@/components/dashboard/PageHeader"
import { ShapCard } from "@/components/disease/ShapCard"
import { Field } from "@/components/ui/field"
import { StatusBadge, type StatusTone } from "@/components/ui/status-badge"

const sectionLabel = "text-2xs font-semibold tracking-wide text-muted-foreground uppercase"

const SEVERITY_TONE: Record<string, StatusTone> = { None: "success", Mild: "warning", "Mod/Sev": "danger" }

function percent(value: number) {
    return `${Math.round(value * 100)}%`
}

/** Input-check errors and warnings, as returned by the server. */
export function InputIssues({ title, issues, tone }: { title: string; issues: InputIssue[]; tone: "error" | "warning" }) {
    if (issues.length === 0) return null
    return (
        <div role="alert" className={tone === "error" ? alertError : alertWarning}>
            <p className="font-medium">{title}</p>
            <ul className="mt-1 list-disc pl-5">
                {issues.map((issue, index) => (
                    <li key={`${issue.code}-${issue.field ?? index}`}>{issue.message}</li>
                ))}
            </ul>
        </div>
    )
}

/**
 * The v2 disease report: findings, severity, image quality and Grad-CAM maps.
 * `originalUrl` is the uploaded image, shown in place of a heat map on request.
 */
export function DiseaseResults({ result, originalUrl = null }: { result: DiseaseAnalyzeResponse; originalUrl?: string | null }) {
    const diseases = result.diseases ?? []
    const detected = diseases.filter((d) => d.detected)
    const check = result.inputCheck
    const notRecorded = result.measurementsNotRecorded ?? []

    return (
        <section aria-labelledby="disease-results-title" className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 id="disease-results-title" className="flex items-center gap-3 text-sm font-semibold">
                    Results for case <span className="font-mono">{result.caseId}</span>
                    {result.reliable
                        ? <StatusBadge tone="success">Completed</StatusBadge>
                        : <StatusBadge tone="warning">{check?.forced ? "Forced — not reliable" : "Review with caution"}</StatusBadge>}
                </h2>
                <p className="text-2xs text-muted-foreground">Research tool — not a medical diagnosis.</p>
            </div>

            {check?.forced && (
                <InputIssues tone="error" title="The inputs failed these checks; the analysis was run anyway and is NOT reliable:" issues={check.errors} />
            )}
            {check && <InputIssues tone="warning" title="Warnings:" issues={check.warnings} />}

            <div className="grid gap-6 lg:grid-cols-2">
                <Card title="Disease findings">
                    <ul className="space-y-3">
                        {diseases.map((finding) => (
                            <FindingRow key={finding.code} finding={finding} />
                        ))}
                    </ul>
                </Card>

                <Card title="Severity">
                    <div className="space-y-4">
                        <dl className="grid grid-cols-2 gap-4">
                            <Field label="Overall severity" value={result.overallSeverity === "None" ? "None (normal)" : result.overallSeverity} />
                            <Field label="Diseases found" value={detected.length === 0 ? "None" : String(detected.length)} />
                        </dl>
                        {(result.severity ?? []).length > 0 ? (
                            <ul className="space-y-2 border-t border-border pt-4">
                                {result.severity!.map((s) => (
                                    <li key={s.group} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                                        <span>
                                            <span className="font-medium">{s.label}</span>
                                            <span className="text-muted-foreground"> ({s.diseases.join(", ")})</span>
                                        </span>
                                        <span className="flex items-center gap-2">
                                            {s.probability !== null && (
                                                <span className="text-xs text-muted-foreground tabular-nums">
                                                    P(Mod/Sev) {percent(s.probability)}
                                                </span>
                                            )}
                                            <StatusBadge tone={SEVERITY_TONE[s.grade] ?? "neutral"}>{s.grade}</StatusBadge>
                                        </span>
                                    </li>
                                ))}
                            </ul>
                        ) : (
                            <p className="text-sm text-muted-foreground">No disease detected, so no severity is graded.</p>
                        )}
                    </div>
                </Card>

                {result.imageQuality && <QualityCard quality={result.imageQuality} />}

                <Card title="Inputs used">
                    <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                        {/* ECD_Deficit is derived from ECD for the model only; not shown to clinicians. */}
                        {Object.entries(result.measurementsUsed ?? {}).filter(([name]) => name !== "ECD_Deficit").map(([name, value]) => (
                            <Field key={name} label={measurementLabel(name)}
                                value={value === null ? null : value.toLocaleString("en-GB")} />
                        ))}
                    </dl>
                    {notRecorded.length > 0 && (
                        <p className="mt-3 text-xs text-muted-foreground">
                            Not recorded: {notRecorded.map(measurementLabel).join(", ")}
                        </p>
                    )}
                </Card>
            </div>

            {detected.some((d) => d.gradcamPng) && (
                <Card title="Why these results: image analysis" description="Where in the image the model found the evidence for each detected disease. An aid for review, not proof of the finding.">
                    <div className="space-y-6">
                        <GradcamGuide />
                        {detected.filter((d) => d.gradcamPng).map((d) => (
                            <GradcamPanel key={d.code} finding={d} originalUrl={originalUrl} />
                        ))}
                    </div>
                </Card>
            )}

            <ShapCard result={result} />

            {result.message && <p className="text-xs text-muted-foreground">{result.message}</p>}
        </section>
    )
}

/** Colours of the jet colour map used for the overlays (low -> high). */
const JET_GRADIENT = "linear-gradient(to right, #00007f, #0000ff, #00ffff, #ffff00, #ff0000, #7f0000)"

function GradcamGuide() {
    return (
        <div className="rounded-2xl border border-border bg-sunken p-4 text-xs leading-relaxed">
            <p className="font-semibold text-foreground">How to read these maps</p>
            <div className="mt-2 max-w-sm" aria-hidden="true">
                <div className="h-2.5 rounded-full" style={{ background: JET_GRADIENT }} />
                <div className="mt-1 flex justify-between text-2xs text-muted-foreground">
                    <span>Little influence</span>
                    <span>Most influence</span>
                </div>
            </div>
            <ul className="mt-3 list-disc space-y-1 pl-5 text-muted-foreground">
                <li><span className="font-medium text-foreground">Red and yellow</span> areas raised this disease's score the most; <span className="font-medium text-foreground">blue</span> areas had little effect.</li>
                <li>Check the highlighted area yourself: does it show the features listed for that disease? Use “Show original” to see it without colour.</li>
                <li>The map shows <em>where the model looked</em>, not the outline of a lesion. It is coarse (blocks of about 1/12 of the image width), so edges are approximate.</li>
                <li>If the hottest area is on the image border, a reflection, an out-of-focus patch or overlaid text, treat the finding with extra caution.</li>
                <li>It explains only the image. The CellChek values also contribute to the result.</li>
            </ul>
        </div>
    )
}

const toggleButton = "rounded-full border border-border px-3 py-1 text-xs font-medium hover:bg-muted aria-pressed:bg-muted"

function GradcamPanel({ finding, originalUrl }: { finding: DiseaseFinding; originalUrl: string | null }) {
    const [showOriginal, setShowOriginal] = useState(false)
    const [markRegion, setMarkRegion] = useState(true)
    const explanation = GRADCAM_EXPLANATIONS[finding.code]
    const focus = finding.gradcamFocus
    const cell = focus ? regionCell(focus.region) : null
    const original = showOriginal && originalUrl !== null
    const region = focus ? focus.region.charAt(0).toUpperCase() + focus.region.slice(1) : ""

    return (
        <figure className="grid gap-4 border-t border-border pt-5 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <div className="space-y-2">
                <div className="relative">
                    <img
                        src={original ? originalUrl : `data:image/png;base64,${finding.gradcamPng}`}
                        alt={original ? `Original image (${finding.label})` : `Grad-CAM heat map for ${finding.label}`}
                        className="aspect-[4/3] w-full rounded-2xl border border-border object-cover"
                    />
                    {/* The heat map is 4:3 like the frame, so the grid third lines up with the image. */}
                    {markRegion && cell && (
                        <div
                            data-testid="focus-outline"
                            aria-hidden="true"
                            className="pointer-events-none absolute rounded-lg border-2 border-dashed border-white shadow-[0_0_0_1px_rgba(0,0,0,0.6)]"
                            style={{ top: `${cell.row * 33.333}%`, left: `${cell.col * 33.333}%`, width: "33.333%", height: "33.333%" }}
                        />
                    )}
                </div>
                <div className="flex flex-wrap gap-2">
                    {originalUrl && (
                        <button type="button" aria-pressed={showOriginal} onClick={() => setShowOriginal((v) => !v)} className={toggleButton}>
                            {showOriginal ? "Show heat map" : "Show original"}
                        </button>
                    )}
                    {cell && (
                        <button type="button" aria-pressed={markRegion} onClick={() => setMarkRegion((v) => !v)} className={toggleButton}>
                            Mark region
                        </button>
                    )}
                </div>
            </div>
            <figcaption className="space-y-4 text-sm">
                <div className="flex flex-wrap items-start justify-between gap-2">
                    <p className="font-semibold">{finding.label}</p>
                    <StatusBadge tone="danger">Found · {percent(finding.probability)}</StatusBadge>
                </div>
                <dl className="space-y-3">
                    {focus && (
                        <div>
                            <dt className={sectionLabel}>Model focus</dt>
                            <dd className="mt-1 flex items-center gap-3">
                                {cell && <RegionGrid row={cell.row} col={cell.col} />}
                                <span>
                                    <span className="font-medium">{region}</span> · {percent(focus.coverage)} of image ({coverageLabel(focus.coverage)})
                                </span>
                            </dd>
                        </div>
                    )}
                    {explanation && (
                        <div>
                            <dt className={sectionLabel}>Look for</dt>
                            <dd>
                                <ul className="mt-1 list-disc space-y-1 pl-5">
                                    {explanation.lookFor.map((point) => <li key={point}>{point}</li>)}
                                </ul>
                            </dd>
                        </div>
                    )}
                </dl>
            </figcaption>
        </figure>
    )
}

/** 3 x 3 thumbnail of the image with the focus cell filled. */
function RegionGrid({ row, col }: { row: number; col: number }) {
    return (
        <span className="grid size-8 shrink-0 grid-cols-3 gap-px rounded-sm border border-border bg-border p-px" aria-hidden="true">
            {Array.from({ length: 9 }, (_, i) => (
                <span key={i} className={Math.floor(i / 3) === row && i % 3 === col ? "bg-destructive" : "bg-card"} />
            ))}
        </span>
    )
}

function FindingRow({ finding }: { finding: DiseaseFinding }) {
    const value = Math.round(Math.min(Math.max(finding.probability, 0), 1) * 100)
    return (
        <li>
            <div className="flex items-center justify-between gap-3 text-sm">
                <span className="font-medium">{finding.label}</span>
                <StatusBadge tone={finding.detected ? "danger" : "neutral"}>{finding.detected ? "Found" : "Not found"}</StatusBadge>
            </div>
            <div
                role="meter"
                aria-label={`${finding.label} probability`}
                aria-valuenow={value}
                aria-valuemin={0}
                aria-valuemax={100}
                className="relative mt-1.5 h-1.5 w-full rounded-full bg-muted"
            >
                <div className={`h-1.5 rounded-full ${finding.detected ? "bg-destructive" : "bg-ring"}`} style={{ width: `${value}%` }} />
                <div className="absolute -top-1 h-3.5 w-0.5 bg-foreground/60" style={{ left: `${finding.threshold * 100}%` }} aria-hidden="true" />
            </div>
            <p className="mt-1 text-2xs text-muted-foreground tabular-nums">
                Probability {percent(finding.probability)}
            </p>
        </li>
    )
}

function QualityCard({ quality }: { quality: ImageQuality }) {
    const tone: StatusTone = quality.rating === "OK" ? "success" : quality.rating === "Low" ? "warning" : "danger"
    return (
        <Card title="Image quality" description="Automatic checks of focus and exposure." actions={<StatusBadge tone={tone}>{quality.rating}</StatusBadge>}>
            <dl className="grid grid-cols-2 gap-4">
                <Field label="Focus" value={quality.focus.toFixed(1)} unit={`low below ${quality.focusLowLimit.toFixed(1)}`} />
                <Field label="Dark pixels" value={percent(quality.darkFraction)} />
                <Field label="Saturated pixels" value={percent(quality.saturatedFraction)} />
            </dl>
        </Card>
    )
}
