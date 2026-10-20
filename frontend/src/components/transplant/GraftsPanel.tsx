import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { listGrafts } from "@/api/transplants"
import { Card } from "@/components/dashboard/PageHeader"
import { GraftFollowupPanel } from "@/components/transplant/GraftFollowupPanel"
import { EmptyState } from "@/components/ui/empty-state"
import { Spinner } from "@/components/ui/spinner"
import { StatusBadge, type StatusTone } from "@/components/ui/status-badge"
import { alertError, tableCell, tableHead, tableHeaderCell, tableRow } from "@/lib/styles"

const ALERT_TONES: Record<string, StatusTone> = { green: "success", amber: "warning", red: "danger" }

/** Every graft (allocated cornea), newest first; choose one to record its visits and follow-up. */
export function GraftsPanel() {
    const grafts = useQuery({ queryKey: ["grafts"], queryFn: () => listGrafts() })
    const [selected, setSelected] = useState<string | null>(null)
    const graft = grafts.data?.find((g) => g.id === selected)

    return (
        <div className="space-y-6">
            <Card title="Grafts" description="Corneas allocated to a recipient request on the Recipients & matching page.">
                {grafts.isPending && <Spinner />}
                {grafts.isError && <p role="alert" className={alertError}>{grafts.error.message}</p>}
                {grafts.isSuccess && grafts.data.length === 0 && (
                    <EmptyState title="No grafts yet" description="Allocate a signed-off cornea to a recipient request to follow it up here." />
                )}
                {grafts.isSuccess && grafts.data.length > 0 && (
                    <div className="-mx-5 -mb-5 overflow-x-auto sm:-mx-6 sm:-mb-6">
                        <table className="w-full text-sm">
                            <thead className={tableHead}>
                                <tr>
                                    <th className={tableHeaderCell}>Tissue ID</th>
                                    <th className={tableHeaderCell}>Request</th>
                                    <th className={tableHeaderCell}>Procedure</th>
                                    <th className={tableHeaderCell}>Surgery</th>
                                    <th className={tableHeaderCell}>Visits</th>
                                    <th className={tableHeaderCell}>Latest alert</th>
                                    <th className={tableHeaderCell}><span className="sr-only">Open</span></th>
                                </tr>
                            </thead>
                            <tbody>
                                {grafts.data.map((g) => (
                                    <tr key={g.id} className={tableRow}>
                                        <td className={`${tableCell} font-mono font-semibold`}>{g.tissueId}</td>
                                        <td className={tableCell}>{g.requestId}</td>
                                        <td className={tableCell}>{g.procedure}</td>
                                        <td className={tableCell}>{g.surgeryDate ? new Date(g.surgeryDate).toLocaleDateString("en-GB") : "—"}</td>
                                        <td className={tableCell}>{g.visits.map((v) => `${v.month}m`).join(", ") || "—"}</td>
                                        <td className={tableCell}>
                                            {g.latestFollowup?.alert
                                                ? <StatusBadge tone={ALERT_TONES[g.latestFollowup.alert] ?? "neutral"}>{g.latestFollowup.alert}</StatusBadge>
                                                : "—"}
                                        </td>
                                        <td className={tableCell}>
                                            <button type="button" className="text-sm font-medium text-accent hover:underline"
                                                aria-pressed={selected === g.id} onClick={() => setSelected(selected === g.id ? null : g.id)}>
                                                {selected === g.id ? "Close" : "Follow up"}
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </Card>
            {graft && <GraftFollowupPanel key={graft.id} graft={graft} />}
        </div>
    )
}
