import { useId, useState, type ChangeEvent } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
    applyCaseImport,
    checkCaseImport,
    downloadImportTemplate,
    type ImportMode,
    type ImportReport,
    type ImportRow,
} from "@/api/cases"
import { Card } from "@/components/dashboard/PageHeader"
import { Spinner } from "@/components/ui/spinner"
import { StatusBadge, type StatusTone } from "@/components/ui/status-badge"
import { ApiError } from "@/lib/api-client"
import { alertError, alertWarning, primaryButton, tableCell, tableHead, tableHeaderCell, textInput } from "@/lib/styles"

const ACCEPT = ".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
const MAX_BYTES = 5 * 1024 * 1024

/**
 * No answer from the server (network error, proxy timeout or gateway error): the import may still be
 * running or may have finished, so the outcome is unknown and importing again could clash with it.
 */
function outcomeUnknown(error: Error): boolean {
    return error instanceof ApiError && [0, 502, 503, 504].includes(error.status)
}

const ACTIONS: Record<ImportRow["action"], { label: string; tone: StatusTone }> = {
    create: { label: "New case", tone: "success" },
    update: { label: "Update", tone: "info" },
    skip: { label: "Exists, skipped", tone: "neutral" },
    error: { label: "Error", tone: "danger" },
}

/**
 * Bulk import of cases from CSV or Excel: check the file first (nothing changes), then import it.
 * The import is all or nothing: it only runs when no row has an error. Images are added per case.
 */
export function ImportCasesCard() {
    const queryClient = useQueryClient()
    const [file, setFile] = useState<File | null>(null)
    const [mode, setMode] = useState<ImportMode>("create")
    const [fileError, setFileError] = useState<string | null>(null)
    const fileId = useId()

    const check = useMutation({ mutationFn: (f: File) => checkCaseImport(f, mode) })
    const apply = useMutation({
        mutationFn: (f: File) => applyCaseImport(f, mode),
        onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["cases"] }),
    })
    const template = useMutation({
        mutationFn: downloadImportTemplate,
        onSuccess: (blob) => {
            const url = URL.createObjectURL(blob)
            const link = document.createElement("a")
            link.href = url
            link.download = "case-import-template.csv"
            link.click()
            URL.revokeObjectURL(url)
        },
    })

    function reset() {
        check.reset()
        apply.reset()
    }

    function handleFile(event: ChangeEvent<HTMLInputElement>) {
        const selected = event.target.files?.[0] ?? null
        reset()
        setFileError(null)
        if (selected && selected.size > MAX_BYTES) {
            setFileError("The file is larger than 5 MB. Split it into smaller files.")
            setFile(null)
            return
        }
        setFile(selected)
        if (selected) check.mutate(selected)
    }

    const report: ImportReport | undefined = apply.data ?? check.data
    const applyUnknown = apply.isError && outcomeUnknown(apply.error)
    // After an unknown outcome the file must be checked again before another import is offered.
    const canImport = check.isSuccess && check.data.withErrors === 0 && check.data.created + check.data.updated > 0
        && !apply.isSuccess && !applyUnknown

    return (
        <Card
            title="Import cases"
            description="Add or update many cases at once from a CSV or Excel (.xlsx) file, one row per cornea. Images are added to each case afterwards."
            actions={
                <button type="button" onClick={() => template.mutate()} disabled={template.isPending}
                    className="text-sm font-medium text-accent hover:underline">
                    Download template
                </button>
            }
        >
            <div className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
                    <div>
                        <label htmlFor={fileId} className="mb-1.5 block text-sm font-medium">File</label>
                        <input id={fileId} type="file" accept={ACCEPT} onChange={handleFile} className={`${textInput} py-2`} />
                        <p className="mt-1.5 text-xs text-muted-foreground">
                            Needs a tissue_id column (e.g. 12656R). Other columns are optional; blank cells are &ldquo;not recorded&rdquo;.
                        </p>
                    </div>
                    <fieldset>
                        <legend className="mb-1.5 text-sm font-medium">Existing tissue IDs</legend>
                        <div className="flex flex-col gap-1 text-sm">
                            {(["create", "update"] as const).map((m) => (
                                <label key={m} className="flex items-center gap-2">
                                    <input type="radio" name="import-mode" value={m} checked={mode === m}
                                        onChange={() => { setMode(m); reset(); if (file) check.mutate(file) }} />
                                    {m === "create" ? "Skip them" : "Update their details (blank cells keep current values)"}
                                </label>
                            ))}
                        </div>
                    </fieldset>
                </div>

                {fileError && <p role="alert" className={alertError}>{fileError}</p>}
                {template.isError && <p role="alert" className={alertError}>{template.error.message}</p>}
                {check.isPending && <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><Spinner /> Checking the file…</p>}
                {check.isError && <p role="alert" className={alertError}>{check.error.message}</p>}
                {apply.isError && (applyUnknown ? (
                    <p role="alert" className={alertWarning}>
                        The server did not confirm the import, so it may still be running or may already have finished.
                        Do not import again yet: wait a minute, then choose the file again. Rows that were imported will
                        show as &ldquo;Exists, skipped&rdquo;.
                    </p>
                ) : (
                    <p role="alert" className={alertError}>The import was not applied: {apply.error.message} Check the file again.</p>
                ))}

                {report && (
                    <>
                        <p role="status" className={report.withErrors > 0 ? alertWarning : "text-sm"}>
                            {report.applied ? "Imported: " : `${report.rows} rows checked: `}
                            {report.created} new, {report.updated} updated, {report.skipped} skipped
                            {report.withErrors > 0 && `, ${report.withErrors} with errors. Fix them and choose the file again; nothing is imported until every row is valid.`}
                        </p>
                        {report.ignoredColumns.length > 0 && (
                            <p className="text-xs text-muted-foreground">Ignored columns: {report.ignoredColumns.join(", ")}</p>
                        )}
                        <div className="-mx-5 max-h-96 overflow-auto sm:-mx-6">
                            <table className="w-full text-sm">
                                <thead className={tableHead}>
                                    <tr>
                                        <th className={tableHeaderCell}>Row</th>
                                        <th className={tableHeaderCell}>Tissue ID</th>
                                        <th className={tableHeaderCell}>Result</th>
                                        <th className={tableHeaderCell}>Problems</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {report.details.map((row) => (
                                        <tr key={row.row}>
                                            <td className={`${tableCell} tabular-nums`}>{row.row}</td>
                                            <td className={`${tableCell} font-mono`}>{row.tissueId ?? "—"}</td>
                                            <td className={tableCell}>
                                                <StatusBadge tone={ACTIONS[row.action].tone}>{ACTIONS[row.action].label}</StatusBadge>
                                            </td>
                                            <td className={tableCell}>
                                                {row.errors.length > 0 && (
                                                    <ul className="list-disc pl-4 text-destructive">
                                                        {row.errors.map((e) => <li key={e}>{e}</li>)}
                                                    </ul>
                                                )}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </>
                )}

                {canImport && file && (
                    <button type="button" onClick={() => apply.mutate(file)} disabled={apply.isPending} className={primaryButton}>
                        {apply.isPending && <Spinner />}
                        Import {check.data.created + check.data.updated} {check.data.created + check.data.updated === 1 ? "case" : "cases"}
                    </button>
                )}
            </div>
        </Card>
    )
}
