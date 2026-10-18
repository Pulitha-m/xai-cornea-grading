import type { EcdReference } from "@/api/analysis"
import { formatCount, formatEcdBand, formatPercent, orderedGrades } from "@/lib/analysis-format"
import { Field } from "@/components/ui/field"

export const sectionLabel = "text-2xs font-semibold tracking-wide text-muted-foreground uppercase"

export function GradeShares({ shares }: { shares: Record<string, number> }) {
    return (
        <ul className="mt-2 flex flex-wrap gap-4 text-sm">
            {orderedGrades(shares).map((grade) => (
                <li key={grade}>
                    <span className="font-semibold">{grade}</span>{" "}
                    <span className="tabular-nums">{formatPercent(shares[grade])}</span>
                </li>
            ))}
        </ul>
    )
}

/** The ECD threshold tree's grade, shown as the single-feature reference the hybrid model was compared with. */
export function EcdReferenceDetails({ reference, showTitle = true }: { reference: EcdReference; showTitle?: boolean }) {
    const title = showTitle && <p className={sectionLabel}>Reference: ECD rule</p>

    if (reference.status.toLowerCase() !== "completed") {
        return (
            <div className="space-y-1">
                {title}
                <p className="text-xs text-muted-foreground">{reference.message}</p>
            </div>
        )
    }

    const distribution = reference.bandDistribution ?? {}
    return (
        <div className="space-y-2">
            {title}
            <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                <Field label="ECD rule grade" value={reference.grade} />
                <Field label="ECD used" value={formatCount(reference.ecdUsed)} unit="cells/mm²" />
                <Field label="ECD band" value={formatEcdBand(reference.ecdBand)} />
            </dl>
            {Object.keys(distribution).length > 0 && (
                <div>
                    <p className="text-xs text-muted-foreground">
                        Recorded grades of the {reference.bandTrainingTissues} training tissues in this band
                    </p>
                    <GradeShares shares={distribution} />
                </div>
            )}
            {reference.reviewRequired && (
                <p className="text-xs text-warning">This ECD is outside the range seen in training.</p>
            )}
        </div>
    )
}
