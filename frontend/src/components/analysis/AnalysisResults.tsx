import type { ReactNode } from "react"
import type { AnalyzeResponse } from "@/api/analysis"
import { formatCount, formatPercent, humanize, isFailed, moduleStatus } from "@/lib/analysis-format"
import { alertError } from "@/lib/styles"
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
                    description="Predicted grade for specialist review — not an eye-bank grading decision."
                    status={grading.status}
                >
                    <div className="flex flex-wrap items-end gap-6">
                        <dl>
                            <Field label="Predicted grade" value={grading.grade} />
                        </dl>
                        <div className="min-w-48 flex-1">
                            <ConfidenceMeter value={grading.confidence} />
                        </div>
                    </div>
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
            ) : (
                children
            )}
        </Card>
    )
}
