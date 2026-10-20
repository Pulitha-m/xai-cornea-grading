import type { MatchResponse } from "@/api/recommendation"
import { alertWarning, tableCell, tableHead, tableHeaderCell, tableRow } from "@/lib/styles"
import { Card } from "@/components/dashboard/PageHeader"
import { StatusBadge } from "@/components/ui/status-badge"

/** Ranked corneas with the reasons for their order, and the corneas that were excluded. */
export function MatchingResults({ result }: { result: MatchResponse }) {
    const ml = result.methodUsed === "ml"

    return (
        <div className="space-y-6">
            <Card
                title={`Ranking for ${result.requestId}`}
                description={ml
                    ? "Ordered by the trained ranker; the MCDA (clinician-weighted) rank is shown for comparison."
                    : "Ordered by the clinician-weighted MCDA score."}
                actions={<StatusBadge tone="info">{ml ? "ML ranker" : "MCDA"}</StatusBadge>}
            >
                <div className="-mx-5 -my-5 overflow-x-auto sm:-mx-6 sm:-my-6">
                    <table className="w-full text-sm">
                        <thead className={tableHead}>
                            <tr>
                                <th className={tableHeaderCell}>Rank</th>
                                <th className={tableHeaderCell}>Tissue</th>
                                <th className={tableHeaderCell}>Grade</th>
                                {ml && <th className={tableHeaderCell}>MCDA rank</th>}
                                <th className={tableHeaderCell}>Why</th>
                                <th className={tableHeaderCell}>Would be #1 if…</th>
                            </tr>
                        </thead>
                        <tbody>
                            {result.ranked.map((c) => (
                                <tr key={c.recordId} className={tableRow}>
                                    <td className={`${tableCell} font-semibold tabular-nums`}>#{c.rank}</td>
                                    <td className={tableCell}>
                                        <div className="font-medium">{c.recordId}</div>
                                        {c.flags.map((f) => <StatusBadge key={f} tone="warning">{f}</StatusBadge>)}
                                    </td>
                                    <td className={tableCell}>{c.grade ?? "–"}</td>
                                    {ml && <td className={`${tableCell} tabular-nums`}>{c.mcdaRank ?? "–"}</td>}
                                    <td className={`${tableCell} text-muted-foreground`}>{c.whyText ?? c.reasons.join(", ")}</td>
                                    <td className={`${tableCell} text-muted-foreground`}>
                                        {c.rank === 1 ? "–" : (c.counterfactual?.replace(/^would be #1 if:\s*/, "") ?? "–")}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </Card>

            {result.excluded.length > 0 && (
                <Card title="Not ranked" description="Excluded before ranking.">
                    <ul className="space-y-1 text-sm">
                        {result.excluded.map((e) => (
                            <li key={e.recordId}>
                                <span className="font-medium">{e.recordId}</span>: {e.reason}
                            </li>
                        ))}
                    </ul>
                </Card>
            )}

            <p className={alertWarning}>{result.disclaimer}</p>
        </div>
    )
}
