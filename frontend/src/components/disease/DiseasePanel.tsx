import { useEffect, useId, useMemo, useState, type ChangeEvent, type FormEvent } from "react"
import { normaliseTissueId, TISSUE_ID_PLACEHOLDER } from "@/lib/tissue-id"
import { IMAGE_ACCEPT, IMAGE_MAX_BYTES } from "@/api/analysis"
import { useDiseaseAnalysis } from "@/hooks/use-disease-analysis"
import { ApiError } from "@/lib/api-client"
import { buildMeasurementPayload, emptyMeasurementInputs, MEASUREMENTS } from "@/lib/disease-measurements"
import { checkImageFile } from "@/lib/image-file"
import { alertError, primaryButton, textInput } from "@/lib/styles"
import { DiseaseResults, InputIssues } from "@/components/disease/DiseaseResults"
import { ReportReader } from "@/components/disease/ReportReader"
import { Card } from "@/components/dashboard/PageHeader"
import { Spinner } from "@/components/ui/spinner"

/** Server error codes that mean "choose a different image" (decoding and corneal-image validation). */
const IMAGE_ERROR_CODES = new Set([
    "UNSUPPORTED_IMAGE_FORMAT",
    "IMAGE_TOO_LARGE",
    "IMAGE_DECODE_FAILED",
    "IMAGE_DIMENSIONS_INVALID",
    "INVALID_IMAGE_DOMAIN",
    "CORNEAL_IMAGE_UNCERTAIN",
])

const MEASUREMENT_NAMES = new Set(MEASUREMENTS.map((m) => m.name))

function measurementErrorsFrom(error: ApiError | null): Record<string, string> {
    return Object.fromEntries(Object.entries(error?.fieldErrors ?? {}).filter(([field]) => MEASUREMENT_NAMES.has(field)))
}

/** Upload a specular microscopy image and five CellChek values for v2 disease detection and severity grading. */
export function DiseasePanel() {
    const analysis = useDiseaseAnalysis()
    const [caseId, setCaseId] = useState("")
    const [file, setFile] = useState<File | null>(null)
    const [fileError, setFileError] = useState<string | null>(null)
    const [values, setValues] = useState(emptyMeasurementInputs)
    const [valueErrors, setValueErrors] = useState<Record<string, string>>({})
    /** Fields whose current value was read from the report and not edited since. */
    const [fromReport, setFromReport] = useState<Set<string>>(() => new Set())
    const fileId = useId()
    const fileHelpId = useId()
    const caseIdId = useId()

    const previewUrl = useMemo(
        () => (file && typeof URL.createObjectURL === "function" ? URL.createObjectURL(file) : null),
        [file],
    )
    useEffect(() => () => {
        if (previewUrl) URL.revokeObjectURL(previewUrl)
    }, [previewUrl])

    const serverError = analysis.error instanceof ApiError ? analysis.error : null
    const imageRejected = serverError?.code != null && IMAGE_ERROR_CODES.has(serverError.code)
    const valuesRejected = Object.keys(measurementErrorsFrom(serverError)).length > 0
    const shownFileError = fileError ?? (imageRejected ? serverError!.message : null)
    const generalError = analysis.isError && !imageRejected && !valuesRejected ? analysis.error.message : null
    const result = analysis.isSuccess ? analysis.data : null
    const checksFailed = result?.status === "input_check_failed"

    function clearResult() {
        analysis.reset()
    }

    async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
        const selected = event.target.files?.[0] ?? null
        clearResult()
        analysis.resetUpload()
        setFile(null)
        setFileError(null)
        if (!selected) return
        const problem = await checkImageFile(selected)
        if (problem) {
            setFileError(problem)
            event.target.value = ""
            return
        }
        setFile(selected)
    }

    function submit(force: boolean) {
        if (!caseId.trim()) return
        if (!file) {
            setFileError((current) => current ?? "Choose a specular microscopy image to analyse.")
            return
        }
        const { payload, errors } = buildMeasurementPayload(values)
        setValueErrors(errors)
        if (Object.keys(errors).length > 0) return
        analysis.mutate({ caseId: normaliseTissueId(caseId), file, measurements: payload, force }, {
            onError: (err) => {
                setValueErrors(measurementErrorsFrom(err instanceof ApiError ? err : null))
                if (err instanceof ApiError && err.code !== null && IMAGE_ERROR_CODES.has(err.code)) {
                    analysis.resetUpload()
                }
            },
        })
    }

    function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        submit(false)
    }

    const busyLabel = analysis.stage === "uploading" ? `Uploading… ${Math.round(analysis.progress * 100)}%` : "Analysing…"

    return (
        <div className="space-y-6">
            <Card title="Run disease screening" description="Submit a specular microscopy image and the CellChek values for disease detection and severity grading.">
                <form className="space-y-4" onSubmit={handleSubmit} noValidate>
                    <div className="grid gap-4 sm:grid-cols-[1fr_12rem]">
                        <div>
                            <label htmlFor={fileId} className="mb-1.5 block text-sm font-medium">Specular microscopy image</label>
                            <input
                                id={fileId}
                                type="file"
                                accept={IMAGE_ACCEPT}
                                onChange={handleFileChange}
                                aria-invalid={shownFileError !== null}
                                aria-describedby={fileHelpId}
                                className={`${textInput} py-2`}
                            />
                        </div>
                        <div>
                            <label htmlFor={caseIdId} className="mb-1.5 block text-sm font-medium">Tissue ID</label>
                            <input
                                id={caseIdId}
                                required
                                value={caseId}
                                onChange={(e) => {
                                    setCaseId(e.target.value)
                                    analysis.resetUpload()
                                    clearResult()
                                }}
                                className={textInput}
                                placeholder={TISSUE_ID_PLACEHOLDER}
                            />
                        </div>
                    </div>

                    <p id={fileHelpId} className="text-xs text-muted-foreground">
                        Greyscale JPEG or PNG, up to {IMAGE_MAX_BYTES / (1024 * 1024)} MB, as exported by the specular
                        microscope (not a screenshot or crop). Other images are rejected.
                    </p>
                    {shownFileError && (
                        <p role="alert" className={alertError}>
                            {shownFileError}
                            {imageRejected && " Choose a different image and try again."}
                        </p>
                    )}

                    {previewUrl && (
                        <img src={previewUrl} alt="Preview of the selected image" className="max-h-48 rounded-2xl border border-border object-contain" />
                    )}

                    <fieldset className="space-y-3 border-t border-border pt-4">
                        <legend className="text-sm font-semibold">CellChek values</legend>
                        <ReportReader
                            caseId={caseId}
                            onRead={(read) => {
                                setValues((current) => ({ ...current, ...read }))
                                setFromReport(new Set(Object.keys(read)))
                                setValueErrors({})
                                clearResult()
                            }}
                            onUseCaseId={(tissueId) => {
                                setCaseId(tissueId)
                                analysis.resetUpload()
                                clearResult()
                            }}
                        />
                        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                            {MEASUREMENTS.map((m) => (
                                <MeasurementField
                                    key={m.name}
                                    label={m.label}
                                    unit={m.unit}
                                    value={values[m.name] ?? ""}
                                    error={valueErrors[m.name] ?? null}
                                    fromReport={fromReport.has(m.name)}
                                    onChange={(value) => {
                                        setValues((current) => ({ ...current, [m.name]: value }))
                                        setFromReport((current) => {
                                            const next = new Set(current)
                                            next.delete(m.name)
                                            return next
                                        })
                                        setValueErrors((current) => {
                                            const next = { ...current }
                                            delete next[m.name]
                                            return next
                                        })
                                        clearResult()
                                    }}
                                />
                            ))}
                        </div>
                    </fieldset>

                    <button type="submit" disabled={analysis.isPending} className={primaryButton}>
                        {analysis.isPending && <Spinner />}
                        {analysis.isPending ? busyLabel : "Analyse"}
                    </button>
                </form>

                {generalError && <p role="alert" className={`mt-4 ${alertError}`}>{generalError}</p>}

                {checksFailed && result.inputCheck && (
                    <div className="mt-4 space-y-3">
                        <InputIssues tone="error" title="No result was produced. Correct these inputs:" issues={result.inputCheck.errors} />
                        <InputIssues tone="warning" title="Warnings:" issues={result.inputCheck.warnings} />
                        <div className="flex flex-wrap items-center gap-3">
                            <button
                                type="button"
                                disabled={analysis.isPending}
                                onClick={() => submit(true)}
                                className="inline-flex h-10 items-center justify-center rounded-full border border-destructive/40 px-5 text-sm font-semibold text-destructive hover:bg-destructive-soft disabled:opacity-70"
                            >
                                Run anyway
                            </button>
                            <p className="text-xs text-muted-foreground">Only if you are sure the inputs are right; the result is marked as not reliable.</p>
                        </div>
                    </div>
                )}
            </Card>

            {result && !checksFailed && <DiseaseResults result={result} originalUrl={previewUrl} />}
        </div>
    )
}

function MeasurementField({ label, unit, value, error, fromReport, onChange }: {
    label: string
    unit?: string
    value: string
    error: string | null
    /** The value was read from the CellChek report and not edited since. */
    fromReport: boolean
    onChange: (value: string) => void
}) {
    const id = useId()
    const errorId = useId()
    return (
        <div>
            <label htmlFor={id} className="mb-1 block text-xs font-medium">
                {label}
                {unit && <span className="font-normal text-muted-foreground"> ({unit})</span>}
                {fromReport && (
                    <span className="ml-1.5 rounded-full bg-accent-soft px-1.5 py-0.5 text-[10px] font-semibold text-accent">
                        From report
                    </span>
                )}
            </label>
            <input
                id={id}
                value={value}
                inputMode="decimal"
                placeholder="Unknown"
                aria-invalid={error !== null}
                aria-describedby={error ? errorId : undefined}
                className={textInput}
                onChange={(e) => onChange(e.target.value)}
            />
            {error && <p id={errorId} role="alert" className="mt-1 text-xs text-destructive">{error}</p>}
        </div>
    )
}
