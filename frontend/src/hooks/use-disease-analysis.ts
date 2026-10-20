import { useRef, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { uploadImage } from "@/api/analysis"
import { analyzeDisease, type DiseaseAnalyzeResponse } from "@/api/disease"
import type { AnalysisStage } from "@/hooks/use-analysis"

export interface DiseaseAnalysisInput {
    caseId: string
    file: File
    /** The five CellChek values; null = not recorded. */
    measurements: Record<string, number | null>
    force: boolean
}

/**
 * Uploads the image (same endpoint as the analysis workspace), then requests the disease analysis by
 * image id. The uploaded image is reused when only the values change, e.g. to correct them or force.
 */
export function useDiseaseAnalysis() {
    const [stage, setStage] = useState<AnalysisStage>("idle")
    const [progress, setProgress] = useState(0)
    const uploaded = useRef<{ file: File; caseId: string; imageId: string } | null>(null)

    const queryClient = useQueryClient()
    const mutation = useMutation<DiseaseAnalyzeResponse, Error, DiseaseAnalysisInput>({
        // New results appear in "Previous results" on the module pages.
        onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["runs"] }),
        mutationFn: async ({ caseId, file, measurements, force }) => {
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
                return await analyzeDisease({ caseId, imageId, measurements, force })
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
