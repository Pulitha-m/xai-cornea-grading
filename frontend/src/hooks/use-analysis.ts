import { useMutation } from "@tanstack/react-query"
import {
    analyzeCornea,
    type AnalyzeRequest,
} from "@/api/analysis"

export function useAnalysis() {
    return useMutation({
        mutationFn: (request: AnalyzeRequest) => analyzeCornea(request),
    })
}