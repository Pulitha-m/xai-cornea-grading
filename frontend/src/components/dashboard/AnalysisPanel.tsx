import { useEffect, useId, useMemo, useState, type ChangeEvent, type FormEvent } from "react"
import { IMAGE_ACCEPT, IMAGE_MAX_BYTES } from "@/api/analysis"
import { useImageAnalysis } from "@/hooks/use-analysis"
import { ApiError } from "@/lib/api-client"
import { parseEcd } from "@/lib/ecd"
import { checkImageFile } from "@/lib/image-file"
import { alertError, primaryButton, textInput } from "@/lib/styles"
import { AnalysisResults } from "@/components/analysis/AnalysisResults"
import { Card } from "@/components/dashboard/PageHeader"
import { Spinner } from "@/components/ui/spinner"

/** Server error codes that mean "choose a different image". */
const IMAGE_ERROR_CODES = new Set([
    "UNSUPPORTED_IMAGE_FORMAT",
    "IMAGE_TOO_LARGE",
    "IMAGE_DECODE_FAILED",
    "IMAGE_DIMENSIONS_INVALID",
    "INVALID_IMAGE_DOMAIN",
    "CORNEAL_IMAGE_UNCERTAIN",
    "IMAGE_QUALITY_INSUFFICIENT",
    "IMAGE_CONTENT_INSUFFICIENT",
])

/** Submits a specular microscopy image to the analysis pipeline (requires the analysis:run permission). */
export function AnalysisPanel() {
    const analysis = useImageAnalysis()
    const [caseId, setCaseId] = useState("")
    const [file, setFile] = useState<File | null>(null)
    const [fileError, setFileError] = useState<string | null>(null)
    const [ecdInput, setEcdInput] = useState("")
    const [ecdError, setEcdError] = useState<string | null>(null)
    const fileId = useId()
    const fileHelpId = useId()
    const fileErrorId = useId()
    const caseIdId = useId()
    const ecdId = useId()
    const ecdHelpId = useId()
    const ecdErrorId = useId()

    const previewUrl = useMemo(
        () => (file && typeof URL.createObjectURL === "function" ? URL.createObjectURL(file) : null),
        [file],
    )
    useEffect(() => () => {
        if (previewUrl) {
            URL.revokeObjectURL(previewUrl)
        }
    }, [previewUrl])

    // Route server rejections to the field they concern.
    const serverError = analysis.error instanceof ApiError ? analysis.error : null
    const imageRejected = serverError?.code != null && IMAGE_ERROR_CODES.has(serverError.code)
    const ecdRejected = serverError?.fieldErrors?.ecd !== undefined
    const shownFileError = fileError ?? (imageRejected ? serverError!.message : null)
    const shownEcdError = ecdError ?? (ecdRejected ? serverError!.fieldErrors.ecd : null)
    const generalError = analysis.isError && !imageRejected && !ecdRejected ? analysis.error.message : null

    async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
        const selected = event.target.files?.[0] ?? null
        analysis.reset()
        analysis.resetUpload()
        setFile(null)
        setFileError(null)
        if (!selected) {
            return
        }
        const problem = await checkImageFile(selected)
        if (problem) {
            setFileError(problem)
            event.target.value = ""
            return
        }
        setFile(selected)
    }

    function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        if (!caseId.trim()) {
            return
        }
        if (!file) {
            setFileError((current) => current ?? "Choose a specular microscopy image to analyse.")
            return
        }
        const { ecd, error } = parseEcd(ecdInput)
        setEcdError(error)
        if (error) {
            return
        }
        analysis.mutate({ caseId: caseId.trim(), file, ecd }, {
            onError: (err) => {
                if (err instanceof ApiError && err.code !== null && IMAGE_ERROR_CODES.has(err.code)) {
                    analysis.resetUpload() // the next attempt uploads the replacement image
                }
            },
        })
    }

    const busyLabel = analysis.stage === "uploading"
        ? `Uploading… ${Math.round(analysis.progress * 100)}%`
        : "Analysing…"

    return (
        <div className="space-y-6">
            <Card title="Run corneal analysis" description="Submit a specular microscopy image for AI-assisted assessment.">
                <form className="space-y-4" onSubmit={handleSubmit} noValidate>
                    <div className="grid gap-4 sm:grid-cols-[1fr_12rem_10rem]">
                        <div>
                            <label htmlFor={fileId} className="mb-1.5 block text-sm font-medium">
                                Specular microscopy image
                            </label>
                            <input
                                id={fileId}
                                type="file"
                                accept={IMAGE_ACCEPT}
                                onChange={handleFileChange}
                                aria-invalid={shownFileError !== null}
                                aria-describedby={shownFileError ? `${fileHelpId} ${fileErrorId}` : fileHelpId}
                                className={`${textInput} py-2`}
                            />
                        </div>
                        <div>
                            <label htmlFor={caseIdId} className="mb-1.5 block text-sm font-medium">
                                Case ID
                            </label>
                            <input
                                id={caseIdId}
                                required
                                value={caseId}
                                onChange={(e) => {
                                    setCaseId(e.target.value)
                                    analysis.resetUpload()
                                }}
                                className={textInput}
                                placeholder="CASE-001"
                            />
                        </div>
                        <div>
                            <label htmlFor={ecdId} className="mb-1.5 block text-sm font-medium">
                                ECD (cells/mm²)
                            </label>
                            <input
                                id={ecdId}
                                inputMode="decimal"
                                value={ecdInput}
                                onChange={(e) => {
                                    setEcdInput(e.target.value)
                                    setEcdError(null)
                                }}
                                aria-invalid={shownEcdError !== null}
                                aria-describedby={shownEcdError ? `${ecdHelpId} ${ecdErrorId}` : ecdHelpId}
                                className={textInput}
                                placeholder="Optional"
                            />
                        </div>
                    </div>

                    <p id={fileHelpId} className="text-xs text-muted-foreground">
                        JPEG or PNG, up to {IMAGE_MAX_BYTES / (1024 * 1024)} MB. The image must show the corneal
                        endothelium; other images are rejected.
                    </p>
                    {shownFileError && (
                        <p id={fileErrorId} role="alert" className={alertError}>
                            {shownFileError}
                            {imageRejected && " Choose a different image and try again."}
                        </p>
                    )}

                    <p id={ecdHelpId} className="text-xs text-muted-foreground">
                        Enter ECD from the specular microscopy report to receive an ECD-based grade. Leave it blank if
                        unavailable; the case will be marked for manual grading.
                    </p>
                    {shownEcdError && (
                        <p id={ecdErrorId} role="alert" className={alertError}>
                            {shownEcdError}
                        </p>
                    )}

                    {previewUrl && (
                        <img
                            src={previewUrl}
                            alt="Preview of the selected image"
                            className="max-h-48 rounded-2xl border border-border object-contain"
                        />
                    )}

                    <button type="submit" disabled={analysis.isPending} className={primaryButton}>
                        {analysis.isPending && <Spinner />}
                        {analysis.isPending ? busyLabel : "Analyse"}
                    </button>
                </form>

                {generalError && (
                    <p role="alert" className={`mt-4 ${alertError}`}>
                        {generalError}
                    </p>
                )}
            </Card>

            {analysis.isSuccess && <AnalysisResults result={analysis.data} />}
        </div>
    )
}
