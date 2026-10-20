import { useMutation } from "@tanstack/react-query"
import {
    recommendFollowup,
    recommendMatch,
    type FollowupRequest,
    type FollowupResponse,
    type MatchRequest,
    type MatchResponse,
} from "@/api/recommendation"

/** Ranks the corneas in stock for one recipient request. */
export function useMatchRecommendation() {
    return useMutation<MatchResponse, Error, MatchRequest>({ mutationFn: (request) => recommendMatch(request) })
}

/** Follow-up recommendation for a graft at its 12-month visit. */
export function useFollowupRecommendation() {
    return useMutation<FollowupResponse, Error, FollowupRequest>({ mutationFn: (request) => recommendFollowup(request) })
}
