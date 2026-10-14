import type { ReactNode } from "react"
import { cn } from "cn"

const TONES = {
    neutral: { badge: "border-border bg-muted text-muted-foreground", dot: "bg-muted-foreground/60" },
    info: { badge: "border-secondary bg-accent-soft text-accent", dot: "bg-ring" },
    success: { badge: "border-success/20 bg-success-soft text-success", dot: "bg-success" },
    warning: { badge: "border-warning/20 bg-warning-soft text-warning", dot: "bg-warning" },
    danger: { badge: "border-destructive/20 bg-destructive-soft text-destructive", dot: "bg-destructive" },
} as const

export type StatusTone = keyof typeof TONES

/** Pill with a coloured dot; the label carries the meaning, the tone only reinforces it. */
export function StatusBadge({ tone = "neutral", children }: { tone?: StatusTone; children: ReactNode }) {
    return (
        <span
            className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-2xs font-medium whitespace-nowrap",
                TONES[tone].badge,
            )}
        >
            <span className={cn("size-1.5 shrink-0 rounded-full", TONES[tone].dot)} aria-hidden="true" />
            {children}
        </span>
    )
}
