import { Fragment, useId, useState, type FormEvent } from "react"
import { useInfiniteQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { listModuleRuns, MODULE_LABELS, type RunSummary } from "@/api/cases"
import { RunDetailView } from "@/components/cases/CaseHistory"
import { Card } from "@/components/dashboard/PageHeader"
import { EmptyState } from "@/components/ui/empty-state"
import { Spinner } from "@/components/ui/spinner"
import { StatusBadge } from "@/components/ui/status-badge"
import { CASES_PATH } from "@/lib/roles"
import { runHeadline, STATUS_TONES } from "@/lib/run-summary"
import { alertError, tableCell, tableHead, tableHeaderCell, tableRow, textInput } from "@/lib/styles"
import { normaliseTissueId, TISSUE_ID_PLACEHOLDER, tissueIdError } from "@/lib/tissue-id"

const PAGE_SIZE = 10

/**
 * Earlier results of one module, across all cases, newest first: search by tissue ID, load older
 * ones, and open any of them as its full report. The same results are in each case's History tab.
 */
export function PreviousResults({ module }: { module: RunSummary["module"] }) {
    const [search, setSearch] = useState("")
    const [tissueId, setTissueId] = useState<string | null>(null)
    const [searchError, setSearchError] = useState<string | null>(null)
    const [open, setOpen] = useState<string | null>(null)
    const searchId = useId()

    const runs = useInfiniteQuery({
        queryKey: ["runs", module, tissueId],
        queryFn: ({ pageParam }) => listModuleRuns(module, { tissueId: tissueId ?? undefined, before: pageParam, limit: PAGE_SIZE }),
        initialPageParam: undefined as string | undefined,
        getNextPageParam: (last) => last.nextBefore ?? undefined,
    })

    function handleSearch(event: FormEvent) {
        event.preventDefault()
        if (search.trim() === "") {
            setSearchError(null)
            setTissueId(null)
            return
        }
        const error = tissueIdError(search)
        setSearchError(error)
        if (error === null) setTissueId(normaliseTissueId(search))
    }

    const items = runs.data?.pages.flatMap((p) => p.items) ?? []

    return (
        <Card
            title="Previous results"
            description={`Earlier ${MODULE_LABELS[module].toLowerCase()} results, newest first. Search by tissue ID or load older ones.`}
        >
            <form className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-start" onSubmit={handleSearch} noValidate>
                <div className="sm:w-56">
                    <label htmlFor={searchId} className="sr-only">Search by tissue ID</label>
                    <input
                        id={searchId}
                        value={search}
                        onChange={(e) => { setSearch(e.target.value); setSearchError(null) }}
                        placeholder={`Tissue ID, e.g. ${TISSUE_ID_PLACEHOLDER}`}
                        aria-invalid={searchError !== null}
                        className={textInput}
                    />
                </div>
                <button type="submit" className="h-10 rounded-full border border-border px-4 text-sm font-medium hover:bg-sunken">
                    Search
                </button>
                {tissueId && (
                    <button type="button" className="h-10 rounded-full px-4 text-sm font-medium text-accent hover:underline"
                        onClick={() => { setSearch(""); setTissueId(null); setSearchError(null) }}>
                        Show all
                    </button>
                )}
            </form>
            {searchError && <p role="alert" className={`mb-4 ${alertError}`}>{searchError}</p>}

            {runs.isPending && <Spinner />}
            {runs.isError && <p role="alert" className={alertError}>{runs.error.message}</p>}
            {runs.isSuccess && items.length === 0 && (
                <EmptyState
                    title={tissueId ? `No results for ${tissueId}` : "No results yet"}
                    description={tissueId ? "Check the tissue ID, or show all results." : "Results appear here after an analysis has run."}
                />
            )}
            {items.length > 0 && (
                <div className="-mx-5 overflow-x-auto sm:-mx-6">
                    <table className="w-full text-sm">
                        <thead className={tableHead}>
                            <tr>
                                <th className={tableHeaderCell}>When</th>
                                <th className={tableHeaderCell}>Tissue ID</th>
                                <th className={tableHeaderCell}>Status</th>
                                <th className={tableHeaderCell}>Result</th>
                                <th className={tableHeaderCell}><span className="sr-only">Report</span></th>
                            </tr>
                        </thead>
                        <tbody>
                            {items.map(({ run, caseId, tissueId: tissue }) => (
                                <Fragment key={run.id}>
                                    <tr className={tableRow}>
                                        <td className={`${tableCell} whitespace-nowrap`}>{new Date(run.createdAt).toLocaleString("en-GB")}</td>
                                        <td className={tableCell}>
                                            <Link to={`${CASES_PATH}/${caseId}`} className="font-mono font-semibold text-accent hover:underline">{tissue}</Link>
                                        </td>
                                        <td className={tableCell}>
                                            <StatusBadge tone={STATUS_TONES[run.status] ?? "neutral"}>{run.status.replaceAll("_", " ")}</StatusBadge>
                                        </td>
                                        <td className={tableCell}>{runHeadline(run)}</td>
                                        <td className={tableCell}>
                                            <button type="button" className="text-sm font-medium text-accent hover:underline"
                                                aria-expanded={open === run.id}
                                                onClick={() => setOpen(open === run.id ? null : run.id)}>
                                                {open === run.id ? "Hide report" : "View report"}
                                            </button>
                                        </td>
                                    </tr>
                                    {open === run.id && (
                                        <tr>
                                            <td colSpan={5} className={tableCell}>
                                                <RunDetailView caseId={caseId} run={run} />
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
                    Load older results
                </button>
            )}
        </Card>
    )
}
