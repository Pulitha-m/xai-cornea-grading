import { useEffect, useId, useMemo, useState, type ChangeEvent, type FormEvent } from "react"
import { IMAGE_ACCEPT, IMAGE_MAX_BYTES } from "@/api/analysis"
import { useImageAnalysis } from "@/hooks/use-analysis"
import { ApiError } from "@/lib/api-client"
import { buildFeaturePayload, emptyFeatureInputs, FEATURES } from "@/lib/grading-features"
import { checkImageFile } from "@/lib/image-file"
import { alertError, primaryButton, textInput } from "@/lib/styles"
import { AnalysisResults } from "@/components/analysis/AnalysisResults"
import { ClinicalFeaturesFields } from "@/components/analysis/ClinicalFeaturesFields"
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

const FEATURE_NAMES = new Set(FEATURES.map((f) => f.name))

/** Server errors that concern a single clinical feature, keyed by feature name. */
function featureErrorsFrom(error: ApiError | null): Record<string, string> {
    return Object.fromEntries(
        Object.entries(error?.fieldErrors ?? {}).filter(([field]) => FEATURE_NAMES.has(field)),
    )
}

/** Submits a specular microscopy image to the analysis pipeline (requires the analysis:run permission). */
export function AnalysisPanel() {
    const analysis = useImageAnalysis()
    const [caseId, setCaseId] = useState("")
    const [file, setFile] = useState<File | null>(null)
    const [fileError, setFileError] = useState<string | null>(null)
    const [features, setFeatures] = useState(emptyFeatureInputs)
    const [featureErrors, setFeatureErrors] = useState<Record<string, string>>({})
    const fileId = useId()
    const fileHelpId = useId()
    const fileErrorId = useId()
    const caseIdId = useId()
    const featuresHelpId = useId()

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
    const featuresRejected = Object.keys(featureErrorsFrom(serverError)).length > 0
    const shownFileError = fileError ?? (imageRejected ? serverError!.message : null)
    const generalError = analysis.isError && !imageRejected && !featuresRejected ? analysis.error.message : null
    const featureErrorCount = Object.keys(featureErrors).length

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
        const { payload, errors } = buildFeaturePayload(features)
        setFeatureErrors(errors)
        if (Object.keys(errors).length > 0) {
            return
        }
        analysis.mutate({ caseId: caseId.trim(), file, clinicalFeatures: payload }, {
            onError: (err) => {
                // Feature errors are shown at their fields until the field is edited.
                setFeatureErrors(featureErrorsFrom(err instanceof ApiError ? err : null))
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
            <Card title="Run corneal analysis" description="Submit a specular microscopy image and the tissue's clinical features for AI-assisted grading.">
                <form className="space-y-4" onSubmit={handleSubmit} noValidate>
                    <div className="grid gap-4 sm:grid-cols-[1fr_12rem]">
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

                    {previewUrl && (
                        <img
                            src={previewUrl}
                            alt="Preview of the selected image"
                            className="max-h-48 rounded-2xl border border-border object-contain"
                        />
                    )}

                    <div className="space-y-3 border-t border-border pt-4">
                        <div>
                            <h3 className="text-sm font-semibold">Clinical features</h3>
                            <p id={featuresHelpId} className="mt-0.5 text-xs text-muted-foreground">
                                The grade comes from a model trained on these 24 inputs together with the image. Enter what is recorded for this
                                tissue; leave anything unavailable as &ldquo;Not recorded&rdquo; (it is not read as zero
                                or &ldquo;No&rdquo;). The more inputs are missing, the less the grade reflects this tissue.
                            </p>
                        </div>
                        <ClinicalFeaturesFields
                            values={features}
                            errors={featureErrors}
                            onChange={(name, value) => {
                                setFeatures((current) => ({ ...current, [name]: value }))
                                setFeatureErrors((current) => {
                                    const next = { ...current }
                                    delete next[name]
                                    return next
                                })
                            }}
                        />
                        {featureErrorCount > 0 && (
                            <p role="alert" className={alertError}>
                                Correct the {featureErrorCount === 1 ? "highlighted clinical feature" : `${featureErrorCount} highlighted clinical features`} and try again.
                            </p>
                        )}
                    </div>

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
