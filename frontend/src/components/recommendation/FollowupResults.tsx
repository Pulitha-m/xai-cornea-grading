import { useState } from "react"
import type { AlertLevel, FollowupRequest, FollowupResponse } from "@/api/recommendation"
import { useFollowupRecommendation } from "@/hooks/use-recommendation"
import { alertWarning, tableCell, tableHead, tableHeaderCell, tableRow } from "@/lib/styles"
import { Card } from "@/components/dashboard/PageHeader"
import { StatusBadge, type StatusTone } from "@/components/ui/status-badge"
import { DivergingBars, RiskMeter, TrajectoryChart } from "@/components/recommendation/charts"

const ALERT: Record<AlertLevel, { tone: StatusTone; label: string }> = {
    green: { tone: "success", label: "Green" },
    amber: { tone: "warning", label: "Amber" },
    red: { tone: "danger", label: "Red" },
}
const OUTCOME_LABEL = { graft_failure: "Graft failure (ECD < 500)", low_ecd: "ECD below 1000" }

const pct = (x: number) => `${Math.round(x * 100)}%`

function riskOf(result: FollowupResponse, outcome: "graft_failure" | "low_ecd", months: number) {
    return result.risk.find((r) => r.outcome === outcome && r.withinMonths === months)?.probability ?? 0
}

/** Alert, next visit, trajectory chart, risk against thresholds, reasons, what-if and model notes. */
export function FollowupResults({ result, request }: { result: FollowupResponse; request: FollowupRequest }) {
    const alert = ALERT[result.alert]
    const t = result.alertThresholds ?? {}
    const observed = [
        { months: 0, ecd: request.baselineEcd },
        ...(request.visit3m ? [{ months: 3, ecd: request.visit3m.ecd }] : []),
        { months: 6, ecd: request.visit6m.ecd },
        { months: 12, ecd: request.visit12m.ecd },
    ]

    return (
        <div className="space-y-6">
            <Card
                title={`Recommendation for ${result.graftId}`}
                actions={<StatusBadge tone={alert.tone}>{alert.label} alert</StatusBadge>}
            >
                <p className="text-lg font-semibold">Next visit in {result.nextVisitMonths} months</p>
                <ul className="mt-3 list-disc space-y-1 pl-5 text-sm">
                    {result.actions.map((a) => <li key={a}>{a}</li>)}
                </ul>
                <p className="mt-4 text-sm text-muted-foreground">
                    <span className="font-medium text-foreground">Why this alert: </span>
                    {result.rulesFired.length > 0 ? result.rulesFired.join("; ") : "no alert rule was triggered"}
                </p>
            </Card>

            <Card title="ECD trajectory" description="Measured visits and the predicted endothelial cell density, with the uncertainty band.">
                <TrajectoryChart observed={observed} predicted={result.predictedEcd} bandLevel={result.bandLevel} />
                <table className="mt-4 w-full text-sm">
                    <caption className="sr-only">Predicted ECD</caption>
                    <thead className={tableHead}>
                        <tr>
                            <th className={tableHeaderCell}>Month</th>
                            <th className={tableHeaderCell}>Predicted ECD</th>
                            <th className={tableHeaderCell}>{result.bandLevel} band</th>
                        </tr>
                    </thead>
                    <tbody>
                        {result.predictedEcd.map((p) => (
                            <tr key={p.months} className={tableRow}>
                                <td className={tableCell}>{p.months}</td>
                                <td className={`${tableCell} font-semibold tabular-nums`}>{p.ecd}</td>
                                <td className={`${tableCell} tabular-nums text-muted-foreground`}>{p.low}–{p.high}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </Card>

            <div className="grid gap-6 lg:grid-cols-2">
                <Card title="Risk after this visit" description="Recalibrated probability; the black mark is the alert threshold.">
                    <div className="space-y-4">
                        <RiskMeter label="Graft failure within 12 months" probability={riskOf(result, "graft_failure", 12)}
                            threshold={t.red_failure_risk_12m ?? null} thresholdLabel="red" />
                        <RiskMeter label="Graft failure within 24 months" probability={riskOf(result, "graft_failure", 24)}
                            threshold={t.amber_failure_risk_24m ?? null} thresholdLabel="amber" />
                        <RiskMeter label="ECD below 1000 within 24 months" probability={riskOf(result, "low_ecd", 24)}
                            threshold={t.amber_low_ecd_risk_24m ?? null} thresholdLabel="amber" />
                    </div>
                    <table className="mt-5 w-full text-sm">
                        <caption className="sr-only">Risk after this visit</caption>
                        <thead className={tableHead}>
                            <tr>
                                <th className={tableHeaderCell}>Outcome</th>
                                <th className={tableHeaderCell}>Within</th>
                                <th className={tableHeaderCell}>Risk</th>
                            </tr>
                        </thead>
                        <tbody>
                            {result.risk.map((r) => (
                                <tr key={`${r.outcome}-${r.withinMonths}`} className={tableRow}>
                                    <td className={tableCell}>{OUTCOME_LABEL[r.outcome]}</td>
                                    <td className={tableCell}>{r.withinMonths} months</td>
                                    <td className={`${tableCell} font-semibold tabular-nums`}>{pct(r.probability)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </Card>

                <Card title="Why" description="What drives this graft's prediction compared with an average graft.">
                    <div className="space-y-5">
                        {result.reasons.graftFailure.length > 0 && (
                            <DivergingBars
                                title="Graft-failure risk (hazard ratio)"
                                items={result.reasons.graftFailure.map((r) => ({
                                    label: r.reason, value: Math.log(r.hazardRatio), display: `×${r.hazardRatio.toFixed(2)}`,
                                }))}
                                favourablePositive={false}
                                favourableLabel="lowers risk"
                                unfavourableLabel="raises risk"
                            />
                        )}
                        {result.reasons.trajectory.length > 0 && (
                            <DivergingBars
                                title="Predicted 60-month ECD"
                                items={result.reasons.trajectory.map((r) => ({
                                    label: r.reason, value: r.effectPct, display: `${r.effectPct > 0 ? "+" : ""}${r.effectPct}%`,
                                }))}
                                favourablePositive
                                favourableLabel="raises ECD"
                                unfavourableLabel="lowers ECD"
                            />
                        )}
                        {result.counterfactuals.map((c) => (
                            <p key={c} className="text-sm text-muted-foreground">{c}</p>
                        ))}
                    </div>
                </Card>
            </div>

            <WhatIf request={request} current={result} />

            <AboutFollowupModel result={result} />

            <p className={alertWarning}>{result.disclaimer}</p>
        </div>
    )
}

/** Change the 12-month ECD and recalculate: shows how the alert and risk respond. */
function WhatIf({ request, current }: { request: FollowupRequest; current: FollowupResponse }) {
    const whatIf = useFollowupRecommendation()
    const [ecd, setEcd] = useState(request.visit12m.ecd)
    const res = whatIf.isSuccess ? whatIf.data : null

    return (
        <Card title="What if?" description="Change the 12-month ECD and recalculate, to see how the alert and risk respond. Descriptive: the 12-month ECD is a measurement, not a treatment choice.">
            <div className="flex flex-wrap items-end gap-4">
                <label className="min-w-[16rem] flex-1 text-sm font-medium">
                    12-month ECD: <span className="tabular-nums">{ecd}</span> cells/mm²
                    <input type="range" min={300} max={3500} step={50} value={ecd}
                        onChange={(e) => {
                            setEcd(Number(e.target.value))
                            whatIf.reset()
                        }}
                        className="mt-2 block w-full accent-[#0369a1]" />
                </label>
                <button type="button" className="h-10 rounded-full border border-border px-5 text-sm font-semibold hover:bg-sunken"
                    disabled={whatIf.isPending}
                    onClick={() => whatIf.mutate({ ...request, visit12m: { ...request.visit12m, ecd } })}>
                    {whatIf.isPending ? "Recalculating…" : "Recalculate"}
                </button>
            </div>
            {whatIf.isError && <p role="alert" className="mt-3 text-sm text-destructive">{whatIf.error.message}</p>}
            {res && (
                <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
                    <div>
                        <dt className="text-muted-foreground">Alert</dt>
                        <dd className="mt-1 flex items-center gap-2">
                            <StatusBadge tone={ALERT[current.alert].tone}>{ALERT[current.alert].label}</StatusBadge>
                            →
                            <StatusBadge tone={ALERT[res.alert].tone}>{ALERT[res.alert].label}</StatusBadge>
                        </dd>
                    </div>
                    <div>
                        <dt className="text-muted-foreground">Next visit</dt>
                        <dd className="mt-1 font-semibold">{current.nextVisitMonths} → {res.nextVisitMonths} months</dd>
                    </div>
                    <div>
                        <dt className="text-muted-foreground">Graft failure within 24 months</dt>
                        <dd className="mt-1 font-semibold tabular-nums">
                            {pct(riskOf(current, "graft_failure", 24))} → {pct(riskOf(res, "graft_failure", 24))}
                        </dd>
                    </div>
                </dl>
            )}
        </Card>
    )
}

function AboutFollowupModel({ result }: { result: FollowupResponse }) {
    return (
        <details className="rounded-3xl border border-border bg-card px-5 py-4 text-sm shadow-bento sm:px-6">
            <summary className="cursor-pointer font-semibold">About this model</summary>
            <ul className="mt-3 list-disc space-y-1.5 pl-5 text-muted-foreground">
                <li>Research prototype: not yet validated on patient follow-up data. For decision-support research only.</li>
                <li>Predicted ECD: gradient-boosting model with an uncertainty band. Risks: Cox model with recalibrated probabilities.</li>
                <li>Alert thresholds are placeholders until agreed with clinicians (rules {result.rulesVersion ?? "not versioned"}).</li>
                <li>Model {result.model}, version {result.modelVersion}.</li>
            </ul>
        </details>
    )
}
