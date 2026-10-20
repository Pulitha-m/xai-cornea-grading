import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { listCandidates } from "@/api/cases"
import { Card } from "@/components/dashboard/PageHeader"
import { EmptyState } from "@/components/ui/empty-state"
import { Spinner } from "@/components/ui/spinner"
import { StatusBadge } from "@/components/ui/status-badge"
import { CASES_PATH } from "@/lib/roles"
import { alertError, tableCell, tableHead, tableHeaderCell, tableRow } from "@/lib/styles"

/**
 * Signed-off corneas with their confirmed values: what donor–recipient matching will rank. Doctors
 * only, as it shows serology status. Each listing is recorded in the audit log.
 */
export function CandidatesCard() {
    const candidates = useQuery({ queryKey: ["cases", "candidates"], queryFn: listCandidates })

    return (
        <Card title="Signed-off corneas" description="Confirmed values only, as used for donor–recipient matching. A positive serology result excludes a cornea.">
            {candidates.isPending && <Spinner />}
            {candidates.isError && <p role="alert" className={alertError}>{candidates.error.message}</p>}
            {candidates.isSuccess && candidates.data.length === 0 && (
                <EmptyState title="No signed-off corneas" description="Cases appear here once a doctor has signed them off." />
            )}
            {candidates.isSuccess && candidates.data.length > 0 && (
                <div className="-mx-5 -mb-5 overflow-x-auto sm:-mx-6 sm:-mb-6">
                    <table className="w-full text-sm">
                        <thead className={tableHead}>
                            <tr>
                                <th className={tableHeaderCell}>Tissue ID</th>
                                <th className={tableHeaderCell}>Grade</th>
                                <th className={tableHeaderCell}>Finding</th>
                                <th className={tableHeaderCell}>ECD</th>
                                <th className={tableHeaderCell}>Donor age</th>
                                <th className={tableHeaderCell}>Days in storage</th>
                                <th className={tableHeaderCell}>Serology</th>
                            </tr>
                        </thead>
                        <tbody>
                            {candidates.data.map((c) => (
                                <tr key={c.recordId} className={tableRow}>
                                    <td className={tableCell}>
                                        <Link to={`${CASES_PATH}/${c.recordId}`} className="font-mono font-semibold text-accent hover:underline">
                                            {c.tissueId}
                                        </Link>
                                    </td>
                                    <td className={tableCell}>{c.grade}</td>
                                    <td className={tableCell}>{c.diseaseFinding}</td>
                                    <td className={`${tableCell} tabular-nums`}>{c.ecd?.toLocaleString("en-GB") ?? "—"}</td>
                                    <td className={`${tableCell} tabular-nums`}>{c.donorAge ?? "—"}</td>
                                    <td className={`${tableCell} tabular-nums`}>{c.daysInStorage ?? "—"}</td>
                                    <td className={tableCell}>
                                        <StatusBadge tone={c.serologyClear === "Yes" ? "success" : c.serologyClear === "No" ? "danger" : "warning"}>
                                            {c.serologyClear === "Yes" ? "Clear" : c.serologyClear === "No" ? "Positive" : "Unknown"}
                                        </StatusBadge>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </Card>
    )
}
