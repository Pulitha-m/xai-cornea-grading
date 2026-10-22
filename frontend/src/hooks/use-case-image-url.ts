import { useEffect, useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { fetchCaseImage } from "@/api/cases"

/** Fetches the decrypted case image with the session token; a short-lived object URL, null until loaded. */
export function useCaseImageUrl(caseId: string, imageId: string) {
    const blob = useQuery({
        queryKey: ["case", caseId, "image", imageId],
        queryFn: () => fetchCaseImage(caseId, imageId),
        staleTime: Infinity,
        gcTime: 60_000,
    })
    const url = useMemo(
        () => (blob.data && typeof URL.createObjectURL === "function" ? URL.createObjectURL(blob.data) : null),
        [blob.data],
    )
    useEffect(() => () => {
        if (url) URL.revokeObjectURL(url)
    }, [url])
    return { url, isError: blob.isError }
}
