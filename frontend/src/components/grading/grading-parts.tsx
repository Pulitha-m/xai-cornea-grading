import { formatPercent, orderedGrades } from "@/lib/analysis-format"

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
