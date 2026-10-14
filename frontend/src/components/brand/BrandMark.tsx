import { cn } from "cn"

export const BRAND_NAME = "National Eye Bank of Sri Lanka"

/**
 * iTRUST / National Eye Bank of Sri Lanka logo. The wordmark is dark, so on dark
 * backgrounds (`inverted`) it sits on a white card to stay legible.
 */
export function BrandMark({ className, inverted = false }: { className?: string; inverted?: boolean }) {
    const logo = <img src="/nebsl-logo.png" alt={BRAND_NAME} className="h-full w-auto object-contain" />

    if (inverted) {
        return (
            <div className={cn("inline-flex h-14 items-center rounded-2xl bg-white px-3 py-2 shadow-bento", className)}>
                {logo}
            </div>
        )
    }

    return <div className={cn("flex h-10 items-center", className)}>{logo}</div>
}
