import { Fragment, useState } from "react"
import type { MatchResponse, RankedCandidate } from "@/api/recommendation"
import { alertWarning, tableCell, tableHead, tableHeaderCell, tableRow } from "@/lib/styles"
import { Card } from "@/components/dashboard/PageHeader"
import { StatusBadge } from "@/components/ui/status-badge"
import { DivergingBars, ScoreBars } from "@/components/recommendation/charts"

/** Ranked corneas with the reasons for their order, and the corneas that were excluded. */
export function MatchingResults({ result }: { result: MatchResponse }) {
    const ml = result.methodUsed === "ml"
    const [open, setOpen] = useState<string | null>(null)
    const columns = ml ? 7 : 6

    return (
        <div className="space-y-6">
            <Card
                title={`Ranking for ${result.requestId}`}
                description={ml
                    ? "Ordered by the trained ranker; the MCDA (clinician-weighted) rank is shown for comparison."
                    : "Ordered by the clinician-weighted MCDA score."}
                actions={<StatusBadge tone="info">{ml ? "ML ranker" : "MCDA"}</StatusBadge>}
            >
                {!result.endotheliumConsidered && (
                    <p className="mb-4 rounded-2xl border border-border bg-sunken px-3.5 py-3 text-sm text-muted-foreground">
                        This surgery does not transplant the endothelium, so MCDA does not score it
                        {ml ? "; the ML ranker can still weigh it, because it learned from NEBSL's past allocations" : ""}.
                    </p>
                )}
                <div className="-mx-5 -mb-5 overflow-x-auto sm:-mx-6 sm:-mb-6">
                    <table className="w-full text-sm">
                        <thead className={tableHead}>
                            <tr>
                                <th className={tableHeaderCell}>Rank</th>
                                <th className={tableHeaderCell}>Tissue</th>
                                <th className={tableHeaderCell}>Grade</th>
                                {ml && <th className={tableHeaderCell}>MCDA rank</th>}
                                <th className={tableHeaderCell}>Why</th>
                                <th className={tableHeaderCell}>Would be #1 if…</th>
                                <th className={tableHeaderCell}><span className="sr-only">Details</span></th>
                            </tr>
                        </thead>
                        <tbody>
                            {result.ranked.map((c) => (
                                <Fragment key={c.recordId}>
                                    <tr className={tableRow}>
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
                                        <td className={tableCell}>
                                            <button type="button" className="text-sm font-medium text-accent hover:underline"
                                                aria-expanded={open === c.recordId}
                                                aria-label={`Details for ${c.recordId}`}
                                                onClick={() => setOpen(open === c.recordId ? null : c.recordId)}>
                                                {open === c.recordId ? "Hide" : "Details"}
                                            </button>
                                        </td>
                                    </tr>
                                    {open === c.recordId && (
                                        <tr>
                                            <td colSpan={columns} className="border-b border-muted bg-sunken/60 px-5 py-4 sm:px-6">
                                                <CandidateDetails candidate={c} ml={ml} />
                                            </td>
                                        </tr>
                                    )}
                                </Fragment>
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

            <AboutMatchingModel result={result} />

            <p className={alertWarning}>{result.disclaimer}</p>
        </div>
    )
}

function CandidateDetails({ candidate: c, ml }: { candidate: RankedCandidate; ml: boolean }) {
    return (
        <div className="grid gap-6 md:grid-cols-2" role="region" aria-label={`Details for ${c.recordId}`}>
            {ml && c.why.length > 0 ? (
                <DivergingBars
                    title={`Why #${c.rank}: effect compared with the other corneas`}
                    items={c.why.filter((w) => Math.abs(w.effect) >= 0.005).map((w) => ({
                        label: w.reason, value: w.effect, display: `${w.effect > 0 ? "+" : ""}${w.effect.toFixed(2)}`,
                    }))}
                    favourablePositive
                    favourableLabel="pushes up"
                    unfavourableLabel="pushes down"
                />
            ) : (
                <p className="text-sm text-muted-foreground">MCDA reasons: {c.reasons.join(", ")}</p>
            )}
            <div>
                <p className="mb-2 text-xs font-medium">
                    MCDA criterion scores (0–1): total {c.matchScore.toFixed(2)}
                    {ml && c.mcdaRank !== null && ` — ML rank #${c.rank}, MCDA rank #${c.mcdaRank}`}
                </p>
                <ScoreBars scores={c.criterionScores} />
            </div>
        </div>
    )
}

function AboutMatchingModel({ result }: { result: MatchResponse }) {
    const s = result.modelSummary ?? {}
    const w = result.weightsUsed
    return (
        <details className="rounded-3xl border border-border bg-card px-5 py-4 text-sm shadow-bento sm:px-6">
            <summary className="cursor-pointer font-semibold">About this model</summary>
            <ul className="mt-3 list-disc space-y-1.5 pl-5 text-muted-foreground">
                <li>Trained on real NEBSL allocations: for each past request, every cornea that was in stock on the decision date.</li>
                {s.ml_top3 !== undefined && (
                    <li>
                        In cross-validation ({String(s.evaluation ?? "")}) the cornea NEBSL actually allocated was in the top 3 for{" "}
                        {Math.round(Number(s.ml_top3) * 100)}% of requests with the ML ranker and {Math.round(Number(s.mcda_top3) * 100)}% with
                        MCDA. The difference was not statistically significant, so both rankings are shown.
                    </li>
                )}
                <li>
                    MCDA weights used: {Object.entries(w).filter(([, v]) => v > 0)
                        .map(([k, v]) => `${k.replaceAll("_", " ")} ${Math.round(v * 100)}%`).join(", ")}.
                </li>
                <li>Agreement with past decisions is not the same as the clinically best choice; positive serology is always excluded.</li>
                <li>Model {result.model}.</li>
            </ul>
        </details>
    )
}
