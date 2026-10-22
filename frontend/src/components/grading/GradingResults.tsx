import type { GradingAnalyzeResponse } from "@/api/grading"
import { orderedGrades } from "@/lib/analysis-format"
import { FEATURE_GROUPS, FEATURES, formatFeatureValue } from "@/lib/grading-features"
import { alertWarning } from "@/lib/styles"
import { ImageValidationNote } from "@/components/analysis/ImageValidationNote"
import { sectionLabel } from "@/components/grading/grading-parts"
import { GradingExplanationView } from "@/components/grading/GradingExplanation"
import { Card } from "@/components/dashboard/PageHeader"
import { Field } from "@/components/ui/field"
import { StatusBadge } from "@/components/ui/status-badge"

function percent(value: number) {
    return `${Math.round(value * 100)}%`
}

/** The grading report: the hybrid model's grade, what drove it and the inputs used. */
export function GradingResults({ result }: { result: GradingAnalyzeResponse }) {
    const warnings = result.warnings
    const notRecorded = result.featuresNotRecorded

    return (
        <section aria-labelledby="grading-results-title" className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 id="grading-results-title" className="flex items-center gap-3 text-sm font-semibold">
                    Results for case <span className="font-mono">{result.caseId}</span>
                    {result.reviewRequired
                        ? <StatusBadge tone="warning">Review required</StatusBadge>
                        : <StatusBadge tone="success">Completed</StatusBadge>}
                </h2>
                <p className="text-2xs text-muted-foreground">
                    Decision support for specialist review — not an eye-bank grading decision.
                </p>
            </div>

            {result.imageValidation && <ImageValidationNote validation={result.imageValidation} />}

            {warnings.length > 0 && (
                <div role="alert" className={alertWarning}>
                    <p className="font-medium">Check these inputs before relying on the grade:</p>
                    <ul className="mt-1 list-disc pl-5">
                        {warnings.map((warning, index) => (
                            <li key={`${warning.code}-${warning.field ?? index}`}>{warning.message}</li>
                        ))}
                    </ul>
                </div>
            )}

            <Card title="Model grade" description="Hybrid model: 24 Konan and slit-lamp inputs plus image features.">
                <div className="grid gap-6 lg:grid-cols-2">
                    <dl className="grid grid-cols-2 content-start gap-4">
                        <Field label="Predicted grade" value={result.grade} />
                        <Field label="Inputs recorded" value={`${24 - notRecorded.length} of 24`} />
                    </dl>
                    <div className="border-t border-border pt-4 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-6">
                        <p className={sectionLabel}>Share of trees voting for each grade</p>
                        <p className="mt-0.5 text-xs text-muted-foreground">Not calibrated — not a confidence</p>
                        <ul className="mt-3 space-y-3">
                            {orderedGrades(result.modelProbabilities).map((grade) => (
                                <VoteRow key={grade} grade={grade} share={result.modelProbabilities[grade]} predicted={grade === result.grade} />
                            ))}
                        </ul>
                    </div>
                </div>
            </Card>

            {result.explanation
                ? <GradingExplanationView explanation={result.explanation} />
                : <p className="text-xs text-muted-foreground">An explanation of this grade could not be computed. The grade itself is unaffected.</p>}

            <Card title="Inputs used" description="The 24 features as given to the model. Not recorded inputs were handled as in training.">
                <div className="space-y-5">
                    {FEATURE_GROUPS.map((group) => (
                        <div key={group.id}>
                            <p className={sectionLabel}>{group.title}</p>
                            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3 lg:grid-cols-4">
                                {FEATURES.filter((f) => f.group === group.id).map((feature) => (
                                    <div key={feature.name} className="min-w-0">
                                        <dt className="text-xs text-muted-foreground">{feature.label}</dt>
                                        <dd className="text-sm font-medium tabular-nums">
                                            {formatFeatureValue(feature.name, result.featuresUsed[feature.name] ?? null)
                                                ?? <span className="font-normal text-muted-foreground">Not recorded</span>}
                                        </dd>
                                    </div>
                                ))}
                            </dl>
                        </div>
                    ))}
                </div>
            </Card>

            {result.message && <p className="text-xs text-muted-foreground">{result.message}</p>}
        </section>
    )
}

function VoteRow({ grade, share, predicted }: { grade: string; share: number; predicted: boolean }) {
    const value = Math.round(Math.min(Math.max(share, 0), 1) * 100)
    return (
        <li>
            <div className="flex items-center justify-between gap-3 text-sm">
                <span className="font-medium">Grade {grade}</span>
                <span className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground tabular-nums">{percent(share)}</span>
                    {predicted && <StatusBadge tone="info">Predicted</StatusBadge>}
                </span>
            </div>
            <div
                role="meter"
                aria-label={`Share of trees voting ${grade}`}
                aria-valuenow={value}
                aria-valuemin={0}
                aria-valuemax={100}
                className="mt-1.5 h-1.5 w-full rounded-full bg-muted"
            >
                <div className={`h-1.5 rounded-full ${predicted ? "bg-accent" : "bg-ring"}`} style={{ width: `${value}%` }} />
            </div>
        </li>
    )
}
