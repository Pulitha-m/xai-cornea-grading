import { useRef, useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { uploadImage } from "@/api/analysis"
import { analyzeCellular, type CellularAnalyzeResponse } from "@/api/cellular"
import type { AnalysisStage } from "@/hooks/use-analysis"

export interface CellularAnalysisInput {
    caseId: string
    file: File
}

/**
 * Uploads the image (same endpoint as the analysis workspace), then requests the cellular analysis by image id.
 * The uploaded image is reused when the same image is analysed again for the same case.
 */
export function useCellularAnalysis() {
    const [stage, setStage] = useState<AnalysisStage>("idle")
    const [progress, setProgress] = useState(0)
    const uploaded = useRef<{ file: File; caseId: string; imageId: string } | null>(null)

    const mutation = useMutation<CellularAnalyzeResponse, Error, CellularAnalysisInput>({
        mutationFn: async ({ caseId, file }) => {
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
                return await analyzeCellular({ caseId, imageId })
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
