import { useRef, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { analyzeCornea, uploadImage, type AnalyzeResponse } from "@/api/analysis"

export interface ImageAnalysisInput {
    caseId: string
    file: File
    /** All 24 grading features; null = not recorded. */
    clinicalFeatures: Record<string, number | string | null>
}

export type AnalysisStage = "idle" | "uploading" | "analysing"

/**
 * Uploads the image, then requests the analysis by image id. If the same file and case
 * were already uploaded (e.g. retrying after correcting a clinical feature), the stored image is reused.
 */
export function useImageAnalysis() {
    const [stage, setStage] = useState<AnalysisStage>("idle")
    const [progress, setProgress] = useState(0)
    const uploaded = useRef<{ file: File; caseId: string; imageId: string } | null>(null)

    const queryClient = useQueryClient()
    const mutation = useMutation<AnalyzeResponse, Error, ImageAnalysisInput>({
        // New results appear in "Previous results" on the module pages.
        onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["runs"] }),
        mutationFn: async ({ caseId, file, clinicalFeatures }) => {
            try {
                let imageId = uploaded.current?.file === file && uploaded.current.caseId === caseId
                    ? uploaded.current.imageId
                    : null
                if (imageId === null) {
                    setStage("uploading")
                    setProgress(0)
                    const result = await uploadImage(caseId, file, setProgress)
                    imageId = result.imageId
                    uploaded.current = { file, caseId, imageId }
                }
                setStage("analysing")
                return await analyzeCornea({ caseId, imageId, clinicalFeatures })
            } finally {
                setStage("idle")
            }
        },
    })

    /** Forget the uploaded image, e.g. after it was rejected, so a replacement is uploaded fresh. */
    function resetUpload() {
        uploaded.current = null
    }

    return { ...mutation, stage, progress, resetUpload }
}
