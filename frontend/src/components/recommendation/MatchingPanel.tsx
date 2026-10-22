import { useId, useState, type FormEvent } from "react"
import type { MatchRequestInfo, TissueGrade } from "@/api/recommendation"
import { useMatchRecommendation } from "@/hooks/use-recommendation"
import { ApiError } from "@/lib/api-client"
import {
    GRADES, NUMBER_COLUMNS, SEROLOGY, SURGERIES, emptyRow, toCandidates, type CandidateRow,
} from "@/lib/matching-form"
import { studyIdPlaceholder } from "@/lib/study-id"
import { alertError, primaryButton, tableCell, tableHead, tableHeaderCell, textInput } from "@/lib/styles"
import { Card } from "@/components/dashboard/PageHeader"
import { Spinner } from "@/components/ui/spinner"
import { MatchingResults } from "@/components/recommendation/MatchingResults"

const cellInput = `${textInput} h-9 min-w-[5.5rem] px-2.5`

/** Enter a recipient request and the corneas in stock; get them ranked with reasons. */
export function MatchingPanel() {
    const recommendation = useMatchRecommendation()
    // Assigned by the backend on the first ranking; re-ranking keeps it until "New request".
    const [requestId, setRequestId] = useState<string | null>(null)
    const [requestedGrade, setRequestedGrade] = useState<TissueGrade>("A")
    const [surgeryType, setSurgeryType] = useState("PK")
    const [urgency, setUrgency] = useState<NonNullable<MatchRequestInfo["urgency"]>>("Routine")
    const [rows, setRows] = useState<CandidateRow[]>(() => [emptyRow(), emptyRow()])
    const [problems, setProblems] = useState<string[]>([])
    const [invalid, setInvalid] = useState<string[]>([])
    const ids = useId()

    const serverError = recommendation.error instanceof ApiError ? recommendation.error : null
    const generalError = recommendation.isError ? (serverError?.message ?? recommendation.error.message) : null
    const result = recommendation.isSuccess ? recommendation.data : null

    function update(key: number, patch: Partial<CandidateRow>) {
        setRows((current) => current.map((r) => (r.key === key ? { ...r, ...patch } : r)))
        recommendation.reset()
    }

    function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        const { candidates, problems: found, invalid: wrong } = toCandidates(rows)
        if (rows.length === 0) found.push("at least one cornea")
        setProblems(found)
        setInvalid(wrong)
        if (found.length || wrong.length) return
        recommendation.mutate({
            request: { requestId, requestedGrade, surgeryType, urgency },
            candidates,
            topK: null,
            method: "ml",
        }, { onSuccess: (data) => setRequestId(data.requestId) })
    }

    function newRequest() {
        setRequestId(null)
        setRows([emptyRow(), emptyRow()])
        setProblems([])
        setInvalid([])
        recommendation.reset()
    }

    const select = <T extends string>(id: string, label: string, value: T, options: readonly T[], onChange: (v: T) => void,
        names: Partial<Record<T, string>> = {}) => (
        <div>
            <label htmlFor={`${ids}-${id}`} className="mb-1.5 block text-sm font-medium">{label}</label>
            <select
                id={`${ids}-${id}`}
                value={value}
                onChange={(e) => {
                    onChange(e.target.value as T)
                    recommendation.reset()
                }}
                className={textInput}
            >
                {options.map((o) => <option key={o} value={o}>{names[o] ?? o}</option>)}
            </select>
        </div>
    )

    return (
        <div className="space-y-6">
            <Card title="Recipient request" description="The request and every cornea currently in stock. Corneas by study code (R0012), not the NEBSL tissue ID. Unknown values can be left empty.">
                <form className="space-y-5" onSubmit={handleSubmit} noValidate>
                    <div className="grid gap-4 sm:grid-cols-4">
                        <div>
                            <label htmlFor={`${ids}-request`} className="mb-1.5 block text-sm font-medium">Request ID</label>
                            <input
                                id={`${ids}-request`}
                                value={requestId ?? ""}
                                readOnly
                                aria-describedby={`${ids}-request-hint`}
                                className={`${textInput} bg-sunken`}
                                placeholder="New request"
                            />
                            <p id={`${ids}-request-hint`} className="mt-1 text-xs text-muted-foreground">
                                {requestId ? "Re-ranking keeps this ID." : "Assigned automatically when you rank."}
                            </p>
                        </div>
                        {select("grade", "Requested grade", requestedGrade, GRADES, setRequestedGrade)}
                        {select("surgery", "Surgery", surgeryType, SURGERIES, setSurgeryType)}
                        {select("urgency", "Urgency", urgency, ["Routine", "Emergency"] as const, setUrgency)}
                    </div>

                    <div className="-mx-5 overflow-x-auto sm:-mx-6">
                        <table className="w-full text-sm">
                            <caption className="sr-only">Corneas in stock</caption>
                            <thead className={tableHead}>
                                <tr>
                                    <th className={tableHeaderCell} title="Study code: R followed by 4 digits, e.g. R0012. Not the NEBSL tissue ID.">Tissue ID</th>
                                    <th className={tableHeaderCell}>Grade</th>
                                    {NUMBER_COLUMNS.map((c) => (
                                        <th key={c.key} className={tableHeaderCell} title={c.hint}>
                                            {c.label}
                                            <span className="sr-only">. {c.hint}</span>
                                        </th>
                                    ))}
                                    <th className={tableHeaderCell} title="Yes = all infection tests negative; No = a positive test (excluded by the safety rule); Unknown = not yet confirmed.">Serology clear</th>
                                    <th className={tableHeaderCell}><span className="sr-only">Remove</span></th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map((r, i) => (
                                    <tr key={r.key}>
                                        <td className={tableCell}>
                                            <input aria-label={`Tissue ID, row ${i + 1}`} value={r.recordId} placeholder={studyIdPlaceholder("cornea")}
                                                onChange={(e) => update(r.key, { recordId: e.target.value })} className={cellInput} />
                                        </td>
                                        <td className={tableCell}>
                                            <select aria-label={`Grade, row ${i + 1}`} value={r.grade}
                                                onChange={(e) => update(r.key, { grade: e.target.value as CandidateRow["grade"] })}
                                                className={cellInput}>
                                                <option value="">–</option>
                                                {GRADES.map((g) => <option key={g}>{g}</option>)}
                                            </select>
                                        </td>
                                        {NUMBER_COLUMNS.map((c) => (
                                            <td key={c.key} className={tableCell}>
                                                <input aria-label={`${c.short}, row ${i + 1}`} inputMode="decimal" value={r[c.key]}
                                                    onChange={(e) => update(r.key, { [c.key]: e.target.value })} className={cellInput} />
                                            </td>
                                        ))}
                                        <td className={tableCell}>
                                            <select aria-label={`Serology clear, row ${i + 1}`} value={r.serologyClear}
                                                onChange={(e) => update(r.key, { serologyClear: e.target.value as CandidateRow["serologyClear"] })}
                                                className={cellInput}>
                                                {SEROLOGY.map((s) => <option key={s}>{s}</option>)}
                                            </select>
                                        </td>
                                        <td className={tableCell}>
                                            <button type="button" className="text-xs text-muted-foreground hover:text-destructive"
                                                onClick={() => {
                                                    setRows((current) => current.filter((x) => x.key !== r.key))
                                                    recommendation.reset()
                                                }}>
                                                Remove
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    <button type="button" className="text-sm font-medium text-accent hover:underline"
                        onClick={() => setRows((current) => [...current, emptyRow()])}>
                        + Add cornea
                    </button>

                    {problems.length > 0 && (
                        <p role="alert" className={alertError}>Missing or not a number: {problems.join(", ")}.</p>
                    )}
                    {invalid.length > 0 && (
                        <p role="alert" className={alertError}>Not possible: {invalid.join("; ")}.</p>
                    )}
                    {generalError && <p role="alert" className={alertError}>{generalError}</p>}

                    <div className="flex flex-wrap items-center gap-3">
                        <button type="submit" className={primaryButton} disabled={recommendation.isPending}>
                            {recommendation.isPending ? <><Spinner /> Ranking…</> : "Rank corneas"}
                        </button>
                        {requestId && (
                            <button type="button" onClick={newRequest}
                                className="h-10 rounded-full border border-border px-4 text-sm font-medium hover:bg-sunken">
                                New request
                            </button>
                        )}
                    </div>
                </form>
            </Card>
            {result && <MatchingResults result={result} />}
        </div>
    )
}
