import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
    recommendFollowup,
    recommendMatch,
    type FollowupRequest,
    type FollowupResponse,
    type MatchRequest,
    type MatchResponse,
} from "@/api/recommendation"

/** Every run is saved, so the "Previous runs" list is refreshed after each one. */
export const RUNS_KEY = "recommendation-runs"

/** Ranks the corneas in stock for one recipient request. */
export function useMatchRecommendation() {
    const queryClient = useQueryClient()
    return useMutation<MatchResponse, Error, MatchRequest>({
        mutationFn: (request) => recommendMatch(request),
        onSettled: () => queryClient.invalidateQueries({ queryKey: [RUNS_KEY, "match"] }),
    })
}

/** Follow-up recommendation for a graft at its 12-month visit. */
export function useFollowupRecommendation() {
    const queryClient = useQueryClient()
    return useMutation<FollowupResponse, Error, FollowupRequest>({
        mutationFn: (request) => recommendFollowup(request),
        onSettled: () => queryClient.invalidateQueries({ queryKey: [RUNS_KEY, "followup"] }),
    })
}
