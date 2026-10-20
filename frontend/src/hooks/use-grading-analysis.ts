import { useRef, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { uploadImage } from "@/api/analysis"
import { analyzeGrading, type GradingAnalyzeResponse } from "@/api/grading"
import type { AnalysisStage } from "@/hooks/use-analysis"

export interface GradingAnalysisInput {
    caseId: string
    file: File
    /** All 24 grading features; null = not recorded. */
    clinicalFeatures: Record<string, number | string | null>
}

/**
 * Uploads the image (same endpoint as the analysis workspace), then requests the grading by image id.
 * The uploaded image is reused when only the features change, e.g. after correcting one.
 */
export function useGradingAnalysis() {
    const [stage, setStage] = useState<AnalysisStage>("idle")
    const [progress, setProgress] = useState(0)
    const uploaded = useRef<{ file: File; caseId: string; imageId: string } | null>(null)

    const queryClient = useQueryClient()
    const mutation = useMutation<GradingAnalyzeResponse, Error, GradingAnalysisInput>({
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
                return await analyzeGrading({ caseId, imageId, clinicalFeatures })
            } finally {
                setStage("idle")
            }
        },
    })

    function resetUpload() {
        uploaded.current = null
    }

    return { ...mutation, stage, progress, resetUpload }
}
