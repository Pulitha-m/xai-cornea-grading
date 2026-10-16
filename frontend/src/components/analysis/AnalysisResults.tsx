import type { ReactNode } from "react"
import type { AnalyzeResponse, GradingResult, ImageValidation } from "@/api/analysis"
import {
    formatCount,
    formatEcdBand,
    formatPercent,
    humanize,
    isFailed,
    isNotImplemented,
    moduleStatus,
} from "@/lib/analysis-format"
import { alertError, alertWarning } from "@/lib/styles"
import { Card } from "@/components/dashboard/PageHeader"
import { ConfidenceMeter } from "@/components/analysis/ConfidenceMeter"
import { Field } from "@/components/ui/field"
import { StatusBadge } from "@/components/ui/status-badge"

/**
 * Structured view of one analysis run. Each module reports independently, so a
 * failed module is shown as such without hiding the others.
 */
export function AnalysisResults({ result }: { result: AnalyzeResponse }) {
    const { cellular, grading, disease, recommendation } = result
    const overall = moduleStatus(result.status)

    return (
        <section aria-labelledby="analysis-results-title" className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 id="analysis-results-title" className="flex items-center gap-3 text-sm font-semibold">
                    Results for case <span className="font-mono">{result.caseId}</span>
                    <StatusBadge tone={overall.tone}>{overall.label}</StatusBadge>
                </h2>
                <p className="text-2xs text-muted-foreground">
                    AI outputs are decision support. Final decisions rest with the reviewing specialist.
                </p>
            </div>

            {result.imageValidation && <ImageValidationNote validation={result.imageValidation} />}

            <div className="grid gap-6 lg:grid-cols-2">
                <ModuleResult
                    title="Cellular analysis"
                    description="Endothelial cell morphometry from the specular microscopy image."
                    status={cellular.status}
                >
                    <dl className="grid grid-cols-2 gap-4">
                        <Field label="Endothelial cell density" value={formatCount(cellular.ecd)} unit="cells/mm²" />
                        <Field label="Cell count" value={formatCount(cellular.cellCount)} />
                        <Field label="Coefficient of variation" value={formatPercent(cellular.coefficientOfVariation)} />
                        <Field label="Hexagonality" value={formatPercent(cellular.hexagonality)} />
                    </dl>
                </ModuleResult>

                <ModuleResult
                    title="Cornea grade"
                    description="ECD-based grade for specialist review — not an eye-bank grading decision."
                    status={grading.status}
                >
                    <GradingDetails grading={grading} />
                </ModuleResult>

                <ModuleResult
                    title="Disease screening"
                    description="Disease indicators detected in the image and their severity."
                    status={disease.status}
                >
                    <dl className="grid grid-cols-2 gap-4">
                        <Field label="Finding" value={disease.disease && humanize(disease.disease)} />
                        <Field label="Severity" value={disease.severity && humanize(disease.severity)} />
                    </dl>
                    <div className="mt-4">
                        <ConfidenceMeter value={disease.confidence} />
                    </div>
                </ModuleResult>

                <ModuleResult
                    title="Recommendation"
                    description="Suggested next step derived from the module outputs."
                    status={recommendation.status}
                >
                    <dl>
                        <Field label="Recommendation" value={recommendation.recommendation} />
                    </dl>
                    <div className="mt-4">
                        <ConfidenceMeter value={recommendation.confidence} />
                    </div>
                </ModuleResult>
            </div>
        </section>
    )
}

function ImageValidationNote({ validation }: { validation: ImageValidation }) {
    if (validation.domainStatus === "UNVALIDATED_DEV_MODE") {
        return (
            <p role="alert" className={alertWarning}>
                Development mode: this image was not checked by the corneal-image validator. Do not rely on these
                results.
            </p>
        )
    }
    return (
        <p className="text-xs text-muted-foreground">
            Image accepted as a specular microscopy image of the corneal endothelium ({validation.width} ×{" "}
            {validation.height} px).
            {!validation.qualityAssessed && " Image quality and cell detail were not assessed automatically."}
        </p>
    )
}

const GRADE_ORDER = ["A+", "A", "B"]

/**
 * The grade comes from fixed ECD cut points. Instead of a model confidence, it shows the recorded
 * grades of training tissues in the same ECD band, since no calibration has been assessed.
 */
function GradingDetails({ grading }: { grading: GradingResult }) {
    if (grading.status.toLowerCase() === "review_required") {
        return <p className={alertWarning}>{grading.message}</p>
    }

    const distribution = grading.bandDistribution ?? {}
    const grades = GRADE_ORDER.filter((grade) => grade in distribution)

    return (
        <div className="space-y-4">
            <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                <Field label="Predicted grade" value={grading.grade} />
                <Field label="ECD used" value={formatCount(grading.ecdUsed)} unit="cells/mm²" />
                <Field label="ECD band" value={formatEcdBand(grading.ecdBand)} />
            </dl>

            {grades.length > 0 && (
                <div>
                    <p className="text-2xs font-semibold tracking-wide text-muted-foreground uppercase">
                        Recorded grades in this ECD band
                    </p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                        {grading.bandTrainingTissues} training tissues — not model confidence
                    </p>
                    <ul className="mt-2 flex flex-wrap gap-4 text-sm">
                        {grades.map((grade) => (
                            <li key={grade}>
                                <span className="font-semibold">{grade}</span>{" "}
                                <span className="tabular-nums">{formatPercent(distribution[grade])}</span>
                            </li>
                        ))}
                    </ul>
                </div>
            )}

            {grading.reviewRequired && (
                <p role="alert" className={alertWarning}>
                    This ECD is outside the range seen in the training data. Review the grade carefully.
                </p>
            )}

            {grading.message && <p className="text-xs text-muted-foreground">{grading.message}</p>}
        </div>
    )
}

function ModuleResult({
    title,
    description,
    status,
    children,
}: {
    title: string
    description: string
    status: string
    children: ReactNode
}) {
    const { label, tone } = moduleStatus(status)

    return (
        <Card title={title} description={description} actions={<StatusBadge tone={tone}>{label}</StatusBadge>}>
            {isFailed(status) ? (
                // The module's own error text is internal detail; show a neutral message instead.
                <p className={alertError}>
                    This module could not complete the analysis. The other modules are unaffected.
                </p>
            ) : isNotImplemented(status) ? (
                <p className="text-sm text-muted-foreground">This module is not available yet.</p>
            ) : (
                children
            )}
        </Card>
    )
}
