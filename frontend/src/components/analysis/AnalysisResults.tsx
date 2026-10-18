import type { ReactNode } from "react"
import type { AnalyzeResponse, GradingResult } from "@/api/analysis"
import { formatCount, formatPercent, humanize, isFailed, isNotImplemented, moduleStatus } from "@/lib/analysis-format"
import { featureLabel } from "@/lib/grading-features"
import { alertError, alertWarning } from "@/lib/styles"
import { Card } from "@/components/dashboard/PageHeader"
import { ConfidenceMeter } from "@/components/analysis/ConfidenceMeter"
import { ImageValidationNote } from "@/components/analysis/ImageValidationNote"
import { EcdReferenceDetails, GradeShares, sectionLabel } from "@/components/grading/grading-parts"
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
                    description="Grade from the hybrid model (clinical features and image) for specialist review — not an eye-bank grading decision."
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

/**
 * The grade comes from the hybrid random forest (24 features + image). Its tree votes are shown as such: they have
 * not been calibrated, so they are not a confidence. The ECD rule's grade is shown alongside as
 * the single-feature reference the model was compared with.
 */
function GradingDetails({ grading }: { grading: GradingResult }) {
    const warnings = grading.warnings ?? []
    const notRecorded = grading.featuresNotRecorded ?? []

    return (
        <div className="space-y-4">
            <dl className="grid grid-cols-2 gap-4">
                <Field label="Predicted grade" value={grading.grade} />
                <Field label="Inputs recorded" value={`${24 - notRecorded.length} of 24`} />
            </dl>

            {grading.modelProbabilities && Object.keys(grading.modelProbabilities).length > 0 && (
                <div>
                    <p className={sectionLabel}>Share of trees voting for each grade</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">Not calibrated — not a confidence</p>
                    <GradeShares shares={grading.modelProbabilities} />
                </div>
            )}

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

            {notRecorded.length > 0 && (
                <details className="text-xs text-muted-foreground">
                    <summary className="cursor-pointer">
                        {notRecorded.length} input{notRecorded.length === 1 ? "" : "s"} not recorded
                    </summary>
                    <p className="mt-1">{notRecorded.map(featureLabel).join(", ")}</p>
                </details>
            )}

            {grading.ecdReference && (
                <div className="border-t border-border pt-4">
                    <EcdReferenceDetails reference={grading.ecdReference} />
                </div>
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
