import { useEffect, useId, useMemo, useState, type ChangeEvent, type FormEvent } from "react"
import { normaliseTissueId, TISSUE_ID_PLACEHOLDER } from "@/lib/tissue-id"
import { IMAGE_ACCEPT, IMAGE_MAX_BYTES } from "@/api/analysis"
import { useCellularAnalysis } from "@/hooks/use-cellular-analysis"
import { ApiError } from "@/lib/api-client"
import { checkImageFile } from "@/lib/image-file"
import { alertError, primaryButton, textInput } from "@/lib/styles"
import { CellularResults } from "@/components/cellular/CellularResults"
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

/** Upload a specular microscopy image for the cellular analysis (ROI, cells, ECD / CV / HEX). */
export function CellularPanel() {
    const analysis = useCellularAnalysis()
    const [caseId, setCaseId] = useState("")
    const [file, setFile] = useState<File | null>(null)
    const [fileError, setFileError] = useState<string | null>(null)
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
    const shownFileError = fileError ?? (imageRejected ? serverError!.message : null)
    const generalError = analysis.isError && !imageRejected ? analysis.error.message : null
    const result = analysis.isSuccess ? analysis.data : null

    async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
        const selected = event.target.files?.[0] ?? null
        analysis.reset()
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

    function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        if (!caseId.trim()) return
        if (!file) {
            setFileError((current) => current ?? "Choose a specular microscopy image to analyse.")
            return
        }
        analysis.mutate({ caseId: normaliseTissueId(caseId), file }, {
            onError: (err) => {
                if (err instanceof ApiError && err.code !== null && IMAGE_ERROR_CODES.has(err.code)) {
                    analysis.resetUpload()
                }
            },
        })
    }

    const busyLabel = analysis.stage === "uploading"
        ? `Uploading… ${Math.round(analysis.progress * 100)}%`
        : "Analysing… (about 10 s)"

    return (
        <div className="space-y-6">
            <Card title="Run cellular analysis" description="Submit a specular microscopy image: the analysable region is selected automatically, the cells are segmented and measured.">
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
                                    analysis.reset()
                                }}
                                className={textInput}
                                placeholder={TISSUE_ID_PLACEHOLDER}
                            />
                        </div>
                    </div>

                    <p id={fileHelpId} className="text-xs text-muted-foreground">
                        Greyscale JPEG or PNG, up to {IMAGE_MAX_BYTES / (1024 * 1024)} MB, as exported by the specular
                        microscope (1296 × 972, not a screenshot or crop). Other images are rejected.
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

                    <button type="submit" disabled={analysis.isPending} className={primaryButton}>
                        {analysis.isPending && <Spinner />}
                        {analysis.isPending ? busyLabel : "Analyse"}
                    </button>
                </form>

                {generalError && <p role="alert" className={`mt-4 ${alertError}`}>{generalError}</p>}
            </Card>

            {result && <CellularResults result={result} />}
        </div>
    )
}
