import { useId, type ChangeEvent } from "react"
import { useMutation } from "@tanstack/react-query"
import { readCellChekReport, REPORT_ACCEPT, type CellChekReport } from "@/api/disease"
import { ApiError } from "@/lib/api-client"
import { measurementLabel } from "@/lib/disease-measurements"
import { alertError, textInput } from "@/lib/styles"
import { InputIssues } from "@/components/disease/DiseaseResults"
import { Spinner } from "@/components/ui/spinner"

/**
 * Optional: read the five CellChek values from the CellChek report (a picture of it, or the .txt
 * export) and fill the fields. The clinician checks and can edit every value; without a report the
 * values are typed in. The report is never the model's image.
 */
export function ReportReader({ caseId, onRead, onUseCaseId }: {
    caseId: string
    onRead: (values: Record<string, string>) => void
    onUseCaseId: (tissueId: string) => void
}) {
    const inputId = useId()
    const helpId = useId()
    const reading = useMutation<CellChekReport, Error, File>({
        mutationFn: readCellChekReport,
        onSuccess: (report) => {
            const found = Object.entries(report.values).filter(([, v]) => v !== null) as [string, number][]
            onRead(Object.fromEntries(found.map(([name, v]) => [name, String(v)])))
        },
    })

    function handleChange(event: ChangeEvent<HTMLInputElement>) {
        const file = event.target.files?.[0]
        reading.reset()
        if (file) reading.mutate(file)
    }

    const report = reading.data
    const filled = report ? Object.values(report.values).filter((v) => v !== null).length : 0

    return (
        <div className="space-y-2 rounded-2xl border border-dashed border-border p-4">
            <label htmlFor={inputId} className="block text-sm font-medium">
                Fill from CellChek report <span className="font-normal text-muted-foreground">(optional)</span>
            </label>
            <input
                id={inputId}
                type="file"
                accept={REPORT_ACCEPT}
                onChange={handleChange}
                disabled={reading.isPending}
                aria-describedby={helpId}
                className={`${textInput} py-2`}
            />
            <p id={helpId} className="text-xs text-muted-foreground">
                A picture of the CellChek report (JPEG or PNG) or its .txt export. The values are read into the fields
                below for you to check. The report is not stored, and its small cell picture is not used: the
                analysis always uses the specular image uploaded above.
            </p>

            {reading.isPending && (
                <p className="flex items-center gap-2 text-xs text-muted-foreground" role="status">
                    <Spinner /> Reading the report…
                </p>
            )}
            {reading.isError && (
                <p role="alert" className={alertError}>
                    {reading.error instanceof ApiError ? reading.error.message : "The report could not be read."} Enter the
                    values by hand.
                </p>
            )}
            {report && (
                <div className="space-y-2" role="status">
                    <p className="text-sm">
                        Filled {filled} of 5 values from the report
                        {report.tissueId && <> for <span className="font-mono">{report.tissueId}</span></>}
                        {report.eye && <> ({report.eye})</>}. Check each one against the report before analysing.
                    </p>
                    {report.notFound.length > 0 && (
                        <p className="text-xs text-warning">
                            Not found in the report — enter by hand if known: {report.notFound.map(measurementLabel).join(", ")}.
                        </p>
                    )}
                    <InputIssues tone="warning" title="Check these values against the report:" issues={report.warnings} />
                    {report.tissueId && report.tissueId !== caseId.trim() && (
                        <button
                            type="button"
                            onClick={() => onUseCaseId(report.tissueId!)}
                            className="rounded-full border border-border px-3 py-1 text-xs font-medium hover:bg-muted"
                        >
                            Use {report.tissueId} as case ID
                        </button>
                    )}
                </div>
            )}
        </div>
    )
}
