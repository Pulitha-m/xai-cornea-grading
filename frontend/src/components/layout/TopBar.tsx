import type { RefObject } from "react"
import { MenuIcon } from "lucide-react"
import { useAuth } from "@/hooks/use-auth"
import { ROLE_LABELS } from "@/lib/roles"
import { BRAND_NAME, BrandMark } from "@/components/brand/BrandMark"
import { StatusBadge } from "@/components/ui/status-badge"

export function TopBar({
    navOpen,
    onOpenNav,
    menuButtonRef,
}: {
    navOpen: boolean
    onOpenNav: () => void
    menuButtonRef: RefObject<HTMLButtonElement | null>
}) {
    const { user } = useAuth()
    const now = new Date()

    return (
        <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center justify-between gap-4 border-b border-border bg-card/90 px-4 backdrop-blur sm:px-6 lg:px-8">
            <div className="flex min-w-0 items-center gap-3">
                <button
                    ref={menuButtonRef}
                    type="button"
                    onClick={onOpenNav}
                    aria-label="Open navigation"
                    aria-expanded={navOpen}
                    aria-controls="mobile-navigation"
                    className="flex size-10 shrink-0 items-center justify-center rounded-2xl border border-border bg-sunken text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40 lg:hidden"
                >
                    <MenuIcon className="size-4" aria-hidden="true" />
                </button>
                <BrandMark className="h-8 lg:hidden" />
                <p className="hidden truncate text-sm font-semibold text-foreground lg:block">{BRAND_NAME}</p>
            </div>

            <div className="flex shrink-0 items-center gap-3">
                <time dateTime={now.toISOString().slice(0, 10)} className="hidden text-xs font-medium text-muted-foreground sm:block">
                    {now.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", year: "numeric" })}
                </time>
                {user && <StatusBadge tone="info">{ROLE_LABELS[user.role]}</StatusBadge>}
            </div>
        </header>
    )
}
