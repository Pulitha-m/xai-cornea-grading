import { Fragment, useId, useState, type FormEvent } from "react"
import { useInfiniteQuery, useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import {
    getRecommendationRun,
    listRecommendationRuns,
    type FollowupRequest,
    type FollowupResponse,
    type MatchResponse,
    type RecommendationKind,
    type RecommendationRun,
} from "@/api/recommendation"
import { Card } from "@/components/dashboard/PageHeader"
import { FollowupResults } from "@/components/recommendation/FollowupResults"
import { MatchingResults } from "@/components/recommendation/MatchingResults"
import { EmptyState } from "@/components/ui/empty-state"
import { Spinner } from "@/components/ui/spinner"
import { StatusBadge, type StatusTone } from "@/components/ui/status-badge"
import { RUNS_KEY } from "@/hooks/use-recommendation"
import { SHOW_FOLLOWUP_RISK } from "@/lib/feature-flags"
import { CASES_PATH } from "@/lib/roles"
import { alertError, tableCell, tableHead, tableHeaderCell, tableRow, textInput } from "@/lib/styles"

const PAGE_SIZE = 10
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const ALERT_TONES: Record<string, StatusTone> = { green: "success", amber: "warning", red: "danger" }
const STATUS_TONES: Record<string, StatusTone> = { completed: "success", rejected: "warning", failed: "danger" }
const TEXT: Record<RecommendationKind, { id: string; search: string; empty: string }> = {
    match: { id: "Request ID", search: "Request ID, e.g. Q0012", empty: "Rankings appear here after corneas have been ranked." },
    followup: { id: "Graft ID", search: "Graft ID, e.g. G0012", empty: "Recommendations appear here after a follow-up has run." },
}

/** Corneas and grafts from donor cases are stored by their case or graft UUID: show them briefly. */
function shortId(id: string, what: string) {
    return UUID.test(id) ? `${what} ${id.slice(0, 8)}` : id
}

/**
 * Earlier rankings or follow-up recommendations, newest first: search by request or graft ID, load
 * older ones, and reopen any of them in full. Users without serology access see only their own runs.
 */
export function PreviousRuns({ kind }: { kind: RecommendationKind }) {
    const [search, setSearch] = useState("")
    const [subject, setSubject] = useState<string | null>(null)
    const [open, setOpen] = useState<string | null>(null)
    const searchId = useId()
    const text = TEXT[kind]

    const runs = useInfiniteQuery({
        queryKey: [RUNS_KEY, kind, subject],
        queryFn: ({ pageParam }) => listRecommendationRuns(kind, { subject: subject ?? undefined, before: pageParam, limit: PAGE_SIZE }),
        initialPageParam: undefined as string | undefined,
        getNextPageParam: (last) => last.nextBefore ?? undefined,
    })
    const items = runs.data?.pages.flatMap((p) => p.items) ?? []

    function handleSearch(event: FormEvent) {
        event.preventDefault()
        setSubject(search.trim() === "" ? null : search.trim())
        setOpen(null)
    }

    return (
        <Card
            title="Previous runs"
            description={`Earlier ${kind === "match" ? "rankings" : "follow-up recommendations"}, newest first. Search by ${text.id.toLowerCase()} or load older ones.`}
        >
            <form className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-start" onSubmit={handleSearch} noValidate>
                <div className="sm:w-56">
                    <label htmlFor={searchId} className="sr-only">Search by {text.id.toLowerCase()}</label>
                    <input id={searchId} value={search} onChange={(e) => setSearch(e.target.value)}
                        placeholder={text.search} className={textInput} />
                </div>
                <button type="submit" className="h-10 rounded-full border border-border px-4 text-sm font-medium hover:bg-sunken">
                    Search
                </button>
                {subject && (
                    <button type="button" className="h-10 rounded-full px-4 text-sm font-medium text-accent hover:underline"
                        onClick={() => { setSearch(""); setSubject(null) }}>
                        Show all
                    </button>
                )}
            </form>

            {runs.isPending && <Spinner />}
            {runs.isError && <p role="alert" className={alertError}>{runs.error.message}</p>}
            {runs.isSuccess && items.length === 0 && (
                <EmptyState
                    title={subject ? `No runs for ${subject}` : "No runs yet"}
                    description={subject ? `Check the ${text.id.toLowerCase()}, or show all runs.` : text.empty}
                />
            )}
            {items.length > 0 && (
                <div className="-mx-5 overflow-x-auto sm:-mx-6">
                    <table className="w-full text-sm">
                        <thead className={tableHead}>
                            <tr>
                                <th className={tableHeaderCell}>When</th>
                                <th className={tableHeaderCell}>{text.id}</th>
                                <th className={tableHeaderCell}>Result</th>
                                <th className={tableHeaderCell}>By</th>
                                <th className={tableHeaderCell}><span className="sr-only">Open</span></th>
                            </tr>
                        </thead>
                        <tbody>
                            {items.map((run) => (
                                <Fragment key={run.id}>
                                    <tr className={tableRow}>
                                        <td className={`${tableCell} whitespace-nowrap`}>{new Date(run.createdAt).toLocaleString("en-GB")}</td>
                                        <td className={`${tableCell} font-medium`}>{shortId(run.subjectId, "graft")}</td>
                                        <td className={tableCell}><RunOutcome run={run} /></td>
                                        <td className={`${tableCell} text-muted-foreground`}>{run.requestedBy ?? "–"}</td>
                                        <td className={tableCell}>
                                            {run.status === "completed" && (
                                                <button type="button" className="text-sm font-medium text-accent hover:underline"
                                                    aria-expanded={open === run.id}
                                                    aria-label={`${open === run.id ? "Hide" : "Open"} run ${run.subjectId}`}
                                                    onClick={() => setOpen(open === run.id ? null : run.id)}>
                                                    {open === run.id ? "Hide" : "Open"}
                                                </button>
                                            )}
                                        </td>
                                    </tr>
                                    {open === run.id && (
                                        <tr>
                                            <td colSpan={5} className="border-b border-muted bg-sunken/60 px-5 py-4 sm:px-6">
                                                <RunDetail runId={run.id} />
                                            </td>
                                        </tr>
                                    )}
                                </Fragment>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
            {runs.hasNextPage && (
                <button type="button" disabled={runs.isFetchingNextPage} onClick={() => void runs.fetchNextPage()}
                    className="mt-4 inline-flex h-10 items-center gap-2 rounded-full border border-border px-4 text-sm font-medium hover:bg-sunken">
                    {runs.isFetchingNextPage && <Spinner />}
                    Load older runs
                </button>
            )}
        </Card>
    )
}

function RunOutcome({ run }: { run: RecommendationRun }) {
    if (run.status !== "completed") {
        return (
            <span className="flex flex-wrap items-center gap-2">
                <StatusBadge tone={STATUS_TONES[run.status] ?? "neutral"}>{run.status}</StatusBadge>
                {run.errorCode && <span className="text-xs text-muted-foreground">{run.errorCode.replaceAll("_", " ").toLowerCase()}</span>}
            </span>
        )
    }
    if (run.kind === "followup") {
        if (!SHOW_FOLLOWUP_RISK) return <span>ECD trajectory predicted</span>
        return (
            <span className="flex flex-wrap items-center gap-2">
                {run.alert && <StatusBadge tone={ALERT_TONES[run.alert] ?? "neutral"}>{run.alert} alert</StatusBadge>}
                {run.nextVisitMonths !== null && <span>next visit in {run.nextVisitMonths} months</span>}
            </span>
        )
    }
    return (
        <span>
            {run.topRecordId ? <>Best option <span className="font-medium">{shortId(run.topRecordId, "case")}</span></> : "No eligible cornea"}
            {run.methodUsed && <span className="ml-2 text-xs text-muted-foreground">({run.methodUsed === "ml" ? "ML ranker" : run.methodUsed.toUpperCase()})</span>}
        </span>
    )
}

/** The saved result, shown with the same screen as a new run. */
function RunDetail({ runId }: { runId: string }) {
    const detail = useQuery({ queryKey: [RUNS_KEY, "detail", runId], queryFn: () => getRecommendationRun(runId) })
    if (detail.isPending) return <Spinner />
    if (detail.isError) return <p role="alert" className={alertError}>{detail.error.message}</p>
    const { summary, inputs, result } = detail.data
    if (!result) return <p className="text-sm text-muted-foreground">This run has no stored result.</p>
    // Runs saved before the inputs were stored cannot redraw the measured visits.
    if (summary.kind === "followup" && !inputs) {
        return <p className="text-sm text-muted-foreground">The visit values of this older run were not saved, so it cannot be shown in full.</p>
    }
    return summary.kind === "match" ? (
        <MatchingResults result={result as MatchResponse} labelFor={(recordId) => UUID.test(recordId)
            ? <Link to={`${CASES_PATH}/${recordId}`} className="text-accent hover:underline">{shortId(recordId, "case")}</Link>
            : recordId} />
    ) : (
        <FollowupResults result={result as FollowupResponse} request={inputs as FollowupRequest} />
    )
}
