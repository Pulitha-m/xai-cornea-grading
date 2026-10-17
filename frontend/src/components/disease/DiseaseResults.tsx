import type { DiseaseAnalyzeResponse, DiseaseFinding, ImageQuality, InputIssue } from "@/api/disease"
import { measurementLabel } from "@/lib/disease-measurements"
import { alertError, alertWarning } from "@/lib/styles"
import { Card } from "@/components/dashboard/PageHeader"
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

/** The v2 disease report: findings, severity, image quality and Grad-CAM maps. */
export function DiseaseResults({ result }: { result: DiseaseAnalyzeResponse }) {
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
                <Card title="Disease findings" description="Probability from the image + numbers model. A disease counts as found at or above its threshold.">
                    <ul className="space-y-3">
                        {diseases.map((finding) => (
                            <FindingRow key={finding.code} finding={finding} />
                        ))}
                    </ul>
                </Card>

                <Card title="Severity" description="Severity of each detected disease group; the overall severity is the worst.">
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
                                                    {s.threshold !== null && ` · cut-off ${percent(s.threshold)}`}
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

                <Card title="Inputs used" description="Blank values were filled with the training median, as in training.">
                    <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                        {Object.entries(result.measurementsUsed ?? {}).map(([name, value]) => (
                            <Field key={name} label={name === "ECD_Deficit" ? "ECD deficit (derived)" : measurementLabel(name)}
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

            {detected.length > 0 && (
                <Card title="Grad-CAM explanations" description="Image regions that most raised each detected disease's score (disease model, DenseNet features layer). An aid for review, not proof of the finding.">
                    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                        {detected.filter((d) => d.gradcamPng).map((d) => (
                            <figure key={d.code} className="space-y-1.5">
                                <img
                                    src={`data:image/png;base64,${d.gradcamPng}`}
                                    alt={`Grad-CAM heat map for ${d.label}`}
                                    className="w-full rounded-2xl border border-border"
                                />
                                <figcaption className="text-xs text-muted-foreground">
                                    {d.label} (P = {d.probability.toFixed(2)})
                                </figcaption>
                            </figure>
                        ))}
                    </div>
                </Card>
            )}

            {result.message && <p className="text-xs text-muted-foreground">{result.message}</p>}
        </section>
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
                Probability {percent(finding.probability)} · threshold {percent(finding.threshold)}
            </p>
        </li>
    )
}

function QualityCard({ quality }: { quality: ImageQuality }) {
    const tone: StatusTone = quality.rating === "OK" ? "success" : quality.rating === "Low" ? "warning" : "danger"
    const unusual = quality.unusualDistance > quality.unusualRejectAbove
        ? "Not like the training images"
        : quality.unusualDistance > quality.unusualWarnAbove ? "Unusual" : "Similar to training images"
    return (
        <Card title="Image quality" description="Automatic checks of focus, exposure and similarity to the training images." actions={<StatusBadge tone={tone}>{quality.rating}</StatusBadge>}>
            <dl className="grid grid-cols-2 gap-4">
                <Field label="Focus" value={quality.focus.toFixed(1)} unit={`low below ${quality.focusLowLimit.toFixed(1)}`} />
                <Field label="Dark pixels" value={percent(quality.darkFraction)} />
                <Field label="Saturated pixels" value={percent(quality.saturatedFraction)} />
                <Field label="Similarity" value={unusual} />
            </dl>
            <p className={`mt-3 ${sectionLabel}`}>
                Distance to training images {quality.unusualDistance.toFixed(3)} (warn &gt; {quality.unusualWarnAbove.toFixed(3)},
                reject &gt; {quality.unusualRejectAbove.toFixed(3)})
            </p>
        </Card>
    )
}
