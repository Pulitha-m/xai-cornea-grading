import { Fragment, useState, type ReactNode } from "react"
import type { MatchResponse, RankedCandidate } from "@/api/recommendation"
import { alertWarning, tableCell, tableHead, tableHeaderCell, tableRow } from "@/lib/styles"
import { Card } from "@/components/dashboard/PageHeader"
import { EmptyState } from "@/components/ui/empty-state"
import { StatusBadge } from "@/components/ui/status-badge"
import { DivergingBars, FAVOURABLE, ScoreBars, UNFAVOURABLE } from "@/components/recommendation/charts"
import { DataWarnings } from "@/components/recommendation/DataWarnings"
import { rankReason, type RankReason } from "@/lib/matching-reasons"

/** Ranked corneas with the reasons for their order, and the corneas that were excluded. */
// labelFor shows a record ID as something readable, e.g. a case UUID as its tissue ID with a link.
export function MatchingResults({ result, labelFor }: { result: MatchResponse; labelFor?: (recordId: string) => ReactNode }) {
    const label = (recordId: string) => labelFor?.(recordId) ?? recordId
    const ml = result.methodUsed === "ml"
    const [open, setOpen] = useState<string | null>(null)
    const columns = 5

    return (
        <div className="space-y-6">
            <DataWarnings warnings={result.warnings} />
            <Card
                title={`Ranking for ${result.requestId}`}
                description={ml
                    ? "Ordered by the ranker learned from past NEBSL allocations, and cross-checked against clinician priorities."
                    : "The learned ranker is unavailable, so the corneas are ordered by clinician priorities."}
                actions={<StatusBadge tone="info">{ml ? "Learned ranker" : "Clinician priorities"}</StatusBadge>}
            >
                {!result.endotheliumConsidered && (
                    <p className="mb-4 rounded-2xl border border-border bg-sunken px-3.5 py-3 text-sm text-muted-foreground">
                        This surgery does not transplant the endothelium, so the clinician-priority cross-check does not score it
                        {ml ? "; the learned ranker can still weigh it, because it learned from NEBSL's past allocations" : ""}.
                    </p>
                )}
                {ml && result.ranked.length > 0 && <CrossCheck top={result.ranked[0]} />}
                {result.ranked.length === 0 ? (
                    <EmptyState
                        title="No eligible cornea for this request"
                        description={`All ${result.excluded.length} cornea${result.excluded.length === 1 ? " was" : "s were"} excluded by the safety rule (listed below), so none can be ranked.`}
                    />
                ) : (
                <div className="-mx-5 -mb-5 overflow-x-auto sm:-mx-6 sm:-mb-6">
                    <table className="w-full text-sm">
                        <thead className={tableHead}>
                            <tr>
                                <th className={tableHeaderCell}>Rank</th>
                                <th className={tableHeaderCell}>Tissue</th>
                                <th className={tableHeaderCell}>Grade</th>
                                <th className={tableHeaderCell}>Reason for this rank</th>
                                <th className={tableHeaderCell}><span className="sr-only">Details</span></th>
                            </tr>
                        </thead>
                        <tbody>
                            {result.ranked.map((c, i) => (
                                <Fragment key={c.recordId}>
                                    <tr className={c.rank === 1 ? `${tableRow} bg-success-soft/50` : tableRow}>
                                        <td className={`${tableCell} align-top font-semibold tabular-nums`}>
                                            #{c.rank}
                                            {c.rank === 1 && <div className="mt-1"><StatusBadge tone="success">Best option</StatusBadge></div>}
                                        </td>
                                        <td className={tableCell}>
                                            <div className="font-medium">{label(c.recordId)}</div>
                                            <div className="mt-1 flex flex-wrap gap-1">
                                                {c.flags.map((f) => <StatusBadge key={f} tone="warning">{f}</StatusBadge>)}
                                            </div>
                                        </td>
                                        <td className={tableCell}>{c.grade ?? "–"}</td>
                                        <td className={tableCell}>
                                            <ReasonForRank rank={c.rank} reason={rankReason(result.ranked, i, ml, result.weightsUsed)} />
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
                )}
            </Card>

            {result.excluded.length > 0 && (
                <Card
                    title={`Excluded: not eligible for transplant (${result.excluded.length})`}
                    description="Removed by a safety rule. This is a fixed rule, not a model decision."
                >
                    <ul className="space-y-2 text-sm">
                        {result.excluded.map((e) => (
                            <li key={e.recordId} className="flex flex-wrap items-center gap-2">
                                <span className="font-medium">{label(e.recordId)}</span>
                                <StatusBadge tone="danger">{e.reason.charAt(0).toUpperCase() + e.reason.slice(1)}</StatusBadge>
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

/** Why the cornea holds this position, compared with the cornea directly above it (#1 with #2). */
function ReasonForRank({ rank, reason: r }: { rank: number; reason: RankReason }) {
    const other = `#${r.comparedWith}`
    const title = r.comparedWith === null ? "The only eligible cornea for this request."
        : rank === 1 ? `Best option for this request, ahead of ${other}.`
        : `Ranked below ${other}.`
    const tied = r.comparedWith !== null && (rank === 1 ? r.better.length === 0 : r.worse.length === 0)

    return (
        <div className="min-w-64 space-y-2">
            <p className="flex flex-wrap items-center gap-2 font-medium">
                {title}
                {r.closeCall && <StatusBadge tone="warning">Close call</StatusBadge>}
            </p>
            {tied && <p className="text-muted-foreground">Almost the same as {other}; only very small differences decide the order.</p>}
            {rank === 1 ? (
                <>
                    <Factors label="Stands out for" items={r.better} favourable />
                    <Factors label={`Trade-offs (outweighed; ${other} is stronger here)`} items={r.worse} />
                </>
            ) : (
                <>
                    <Factors label="Held back by" items={r.worse} />
                    <Factors label={`Better than ${other} on (not enough to move up)`} items={r.better} favourable />
                </>
            )}
            {r.serologyNote && <p className="text-xs font-medium text-warning">{r.serologyNote}</p>}
        </div>
    )
}

function Factors({ label, items, favourable = false }: { label: string; items: string[]; favourable?: boolean }) {
    if (items.length === 0) return null
    return (
        <div>
            <p className="mb-1 text-xs text-muted-foreground">{label}:</p>
            <ul className="flex flex-wrap gap-1.5" aria-label={label}>
                {items.map((item) => (
                    <li key={item} className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-0.5 text-xs">
                        <span className="size-1.5 shrink-0 rounded-full" style={{ background: favourable ? FAVOURABLE : UNFAVOURABLE }}
                            aria-hidden="true" />
                        {item}
                    </li>
                ))}
            </ul>
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
                <p className="text-sm text-muted-foreground">Strongest criteria: {c.reasons.join(", ")}</p>
            )}
            <div>
                {ml && c.mcdaRank !== null && (
                    <p className="mb-2 text-sm">
                        <span className="font-medium">Cross-check against clinician priorities:</span> #{c.mcdaRank}
                    </p>
                )}
                <p className="mb-2 text-xs font-medium">Clinician-priority scores (0–1): total {c.matchScore.toFixed(2)}</p>
                <ScoreBars scores={c.criterionScores} />
            </div>
        </div>
    )
}

/** One line above the ranking: where the recommended cornea (#1, highlighted below) stands by clinician priorities. */
function CrossCheck({ top }: { top: RankedCandidate }) {
    if (top.mcdaRank === null) return null
    const agrees = top.mcdaRank === 1
    return (
        <p className={`mb-4 rounded-2xl border px-3.5 py-3 text-sm ${agrees ? "border-success/20 bg-success-soft" : "border-warning/20 bg-warning-soft"}`}>
            <span className="font-medium">Cross-checked against clinician priorities: </span>
            {agrees
                ? "the recommended cornea is also first."
                : `the recommended cornea ranks #${top.mcdaRank}. Review its reasons below before deciding.`}
        </p>
    )
}

function AboutMatchingModel({ result }: { result: MatchResponse }) {
    const s = result.modelSummary ?? {}
    const w = result.weightsUsed
    return (
        <details className="rounded-3xl border border-border bg-card px-5 py-4 text-sm shadow-bento sm:px-6">
            <summary className="cursor-pointer font-semibold">About this model</summary>
            <ul className="mt-3 list-disc space-y-1.5 pl-5 text-muted-foreground">
                <li>Learned from real NEBSL allocations: for each past request, every cornea that was in stock on the decision date.</li>
                {s.ml_top3 !== undefined && (
                    <li>
                        Validated by cross-validation against historical NEBSL allocations ({String(s.evaluation ?? "")}): the cornea
                        NEBSL actually allocated was in the top 3 for {Math.round(Number(s.ml_top3) * 100)}% of requests.
                    </li>
                )}
                <li>
                    Cross-checked against clinician priorities: {Object.entries(w).filter(([, v]) => v > 0)
                        .map(([k, v]) => `${k.replaceAll("_", " ")} ${Math.round(v * 100)}%`).join(", ")}.
                </li>
                <li>Agreement with past decisions is not the same as the clinically best choice; positive serology is always excluded.</li>
                <li>Model {result.model}.</li>
            </ul>
        </details>
    )
}
