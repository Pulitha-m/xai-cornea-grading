import { cn } from "cn"

/** Corneal-AI logo: a stylised iris inside an eye outline. */
export function BrandLogo({ className }: { className?: string }) {
    return (
        <svg viewBox="0 0 32 32" className={cn("size-8", className)} aria-hidden="true">
            <rect width="32" height="32" rx="8" fill="currentColor" />
            <path
                d="M5 16s4-7 11-7 11 7 11 7-4 7-11 7S5 16 5 16Z"
                fill="none"
                stroke="#ffffff"
                strokeWidth="1.6"
                strokeLinejoin="round"
            />
            <circle cx="16" cy="16" r="4" fill="none" stroke="#5eead4" strokeWidth="1.6" />
            <circle cx="16" cy="16" r="1.6" fill="#ffffff" />
        </svg>
    )
}

export function BrandMark({ className, inverted = false }: { className?: string; inverted?: boolean }) {
    return (
        <div className={cn("flex items-center gap-2.5", className)}>
            <BrandLogo className={inverted ? "text-white/10" : "text-primary"} />
            <span className={cn("text-lg font-semibold tracking-tight", inverted ? "text-white" : "text-primary")}>
                Corneal<span className={inverted ? "text-teal-300" : "text-accent"}>-AI</span>
            </span>
        </div>
    )
}
