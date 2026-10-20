import type { AlertLevel, FollowupResponse } from "@/api/recommendation"
import { alertWarning, tableCell, tableHead, tableHeaderCell, tableRow } from "@/lib/styles"
import { Card } from "@/components/dashboard/PageHeader"
import { StatusBadge, type StatusTone } from "@/components/ui/status-badge"

const ALERT: Record<AlertLevel, { tone: StatusTone; label: string }> = {
    green: { tone: "success", label: "Green" },
    amber: { tone: "warning", label: "Amber" },
    red: { tone: "danger", label: "Red" },
}
const OUTCOME_LABEL = { graft_failure: "Graft failure (ECD < 500)", low_ecd: "ECD below 1000" }

const pct = (x: number) => `${Math.round(x * 100)}%`

/** Alert, next visit, predicted ECD with its band, risks and the reasons behind them. */
export function FollowupResults({ result }: { result: FollowupResponse }) {
    const alert = ALERT[result.alert]
    const reasons = [
        ...result.reasons.graftFailure.map((r) => `${r.reason} (hazard ×${r.hazardRatio.toFixed(2)})`),
        ...result.reasons.trajectory.map((r) => `${r.reason} (${r.effectPct > 0 ? "+" : ""}${r.effectPct}% on 60-month ECD)`),
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
                {result.rulesFired.length > 0 && (
                    <p className="mt-4 text-sm text-muted-foreground">
                        <span className="font-medium text-foreground">Why: </span>
                        {result.rulesFired.join("; ")}
                    </p>
                )}
            </Card>

            <div className="grid gap-6 lg:grid-cols-2">
                <Card title="Predicted ECD" description={`Cells/mm² with the ${result.bandLevel} band.`}>
                    <table className="w-full text-sm">
                        <thead className={tableHead}>
                            <tr>
                                <th className={tableHeaderCell}>Month</th>
                                <th className={tableHeaderCell}>Predicted</th>
                                <th className={tableHeaderCell}>Band</th>
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

                <Card title="Risk after this visit" description="Recalibrated probability within 12 and 24 months.">
                    <table className="w-full text-sm">
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
            </div>

            {(reasons.length > 0 || result.counterfactuals.length > 0) && (
                <Card title="Model reasons" description="What drives this graft's prediction compared with an average graft.">
                    {reasons.length > 0 && (
                        <ul className="list-disc space-y-1 pl-5 text-sm">
                            {reasons.map((r) => <li key={r}>{r}</li>)}
                        </ul>
                    )}
                    {result.counterfactuals.map((c) => (
                        <p key={c} className="mt-3 text-sm text-muted-foreground">{c}</p>
                    ))}
                </Card>
            )}

            <p className={alertWarning}>
                {result.disclaimer} Models developed on: {result.dataSource} data
                {result.dataSource === "simulated" ? " (method development)" : ""}. Model {result.modelVersion}
                {result.rulesVersion ? `; alert rules ${result.rulesVersion}` : ""}.
            </p>
        </div>
    )
}
