import { useId, useState, type FormEvent } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { ClipboardListIcon } from "lucide-react"
import { Link, useNavigate } from "react-router-dom"
import { openCase, recentCases } from "@/api/cases"
import { CandidatesCard } from "@/components/cases/CandidatesCard"
import { Card, PageHeader } from "@/components/dashboard/PageHeader"
import { EmptyState } from "@/components/ui/empty-state"
import { Spinner } from "@/components/ui/spinner"
import { useAuth } from "@/hooks/use-auth"
import { CASES_PATH } from "@/lib/roles"
import { alertError, primaryButton, tableCell, tableHead, tableHeaderCell, tableRow, textInput } from "@/lib/styles"
import { normaliseTissueId, TISSUE_ID_HELP, TISSUE_ID_PLACEHOLDER, tissueIdError } from "@/lib/tissue-id"

/** Open a donor case by tissue ID (created on first use), or pick a recently updated one. */
export function CasesPage() {
    const navigate = useNavigate()
    const { user } = useAuth()
    const canSeeCandidates = user?.permissions.includes("serology:access") ?? false
    const [tissueId, setTissueId] = useState("")
    const [fieldError, setFieldError] = useState<string | null>(null)
    const inputId = useId()
    const helpId = useId()
    const errorId = useId()

    const recent = useQuery({ queryKey: ["cases", "recent"], queryFn: recentCases })
    const open = useMutation({
        mutationFn: openCase,
        onSuccess: (opened) => navigate(`${CASES_PATH}/${opened.id}`),
    })

    function handleSubmit(event: FormEvent) {
        event.preventDefault()
        const error = tissueIdError(tissueId)
        setFieldError(error)
        if (error === null) open.mutate(normaliseTissueId(tissueId))
    }

    const shownError = fieldError ?? (open.isError ? open.error.message : null)

    return (
        <>
            <PageHeader
                eyebrow={
                    <>
                        <ClipboardListIcon aria-hidden="true" />
                        Eye bank
                    </>
                }
                title="Donor cases"
                description="One case per donor cornea, identified by its tissue ID. Enter the case details once; every analysis on the case uses them, and every result is kept with the case."
            />
            <div className="space-y-6">
                <Card title="Open a case" description="Opens the case for this tissue ID, or creates it if it does not exist yet.">
                    <form className="flex flex-col gap-3 sm:flex-row sm:items-start" onSubmit={handleSubmit} noValidate>
                        <div className="sm:w-64">
                            <label htmlFor={inputId} className="mb-1.5 block text-sm font-medium">Tissue ID</label>
                            <input
                                id={inputId}
                                value={tissueId}
                                onChange={(e) => {
                                    setTissueId(e.target.value)
                                    setFieldError(null)
                                    open.reset()
                                }}
                                placeholder={TISSUE_ID_PLACEHOLDER}
                                autoComplete="off"
                                aria-invalid={shownError !== null}
                                aria-describedby={shownError ? `${helpId} ${errorId}` : helpId}
                                className={textInput}
                            />
                            <p id={helpId} className="mt-1.5 text-xs text-muted-foreground">{TISSUE_ID_HELP}</p>
                        </div>
                        <button type="submit" disabled={open.isPending} className={`${primaryButton} sm:mt-7`}>
                            {open.isPending && <Spinner />}
                            Open case
                        </button>
                    </form>
                    {shownError && <p id={errorId} role="alert" className={`mt-3 ${alertError}`}>{shownError}</p>}
                </Card>

                <Card title="Recent cases" description="The 20 most recently updated cases.">
                    {recent.isPending && <Spinner />}
                    {recent.isError && <p role="alert" className={alertError}>{recent.error.message}</p>}
                    {recent.isSuccess && recent.data.length === 0 && (
                        <EmptyState title="No cases yet" description="Open a case with its tissue ID to start." />
                    )}
                    {recent.isSuccess && recent.data.length > 0 && (
                        <div className="-mx-5 -mb-5 overflow-x-auto sm:-mx-6 sm:-mb-6">
                            <table className="w-full text-sm">
                                <thead className={tableHead}>
                                    <tr>
                                        <th className={tableHeaderCell}>Tissue ID</th>
                                        <th className={tableHeaderCell}>ECD</th>
                                        <th className={tableHeaderCell}>Images</th>
                                        <th className={tableHeaderCell}>Updated</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {recent.data.map((c) => (
                                        <tr key={c.id} className={tableRow}>
                                            <td className={tableCell}>
                                                <Link to={`${CASES_PATH}/${c.id}`} className="font-mono font-semibold text-accent hover:underline">
                                                    {c.tissueId}
                                                </Link>
                                            </td>
                                            <td className={`${tableCell} tabular-nums`}>
                                                {c.details.ecd === null ? "—" : `${c.details.ecd.toLocaleString("en-GB")} cells/mm²`}
                                            </td>
                                            <td className={`${tableCell} tabular-nums`}>{c.imageCount}</td>
                                            <td className={tableCell}>{new Date(c.updatedAt).toLocaleString("en-GB")}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </Card>

                {canSeeCandidates && <CandidatesCard />}
            </div>
        </>
    )
}
