import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useAuth } from "@/hooks/use-auth"
import { ROLE_LABELS } from "@/lib/roles"
import { LogOutIcon } from "@/components/ui/icons"
import { Spinner } from "@/components/ui/spinner"

function initials(fullName: string): string {
    return fullName
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part[0].toUpperCase())
        .join("")
}

/** Signed-in user's identity and sign-out, pinned to the bottom of the sidebar. */
export function AccountFooter() {
    const { user, logout } = useAuth()
    const navigate = useNavigate()
    const [signingOut, setSigningOut] = useState(false)

    if (!user) {
        return null
    }

    async function handleLogout() {
        setSigningOut(true)
        await logout()
        navigate("/login", { replace: true })
    }

    return (
        <div className="flex shrink-0 items-center gap-3 border-t border-border p-4">
            <span
                aria-hidden="true"
                className="flex size-9 shrink-0 items-center justify-center rounded-full border border-secondary bg-accent-soft text-xs font-semibold text-accent"
            >
                {initials(user.fullName)}
            </span>
            <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-semibold">{user.fullName}</p>
                <p className="truncate text-2xs font-medium text-accent">{ROLE_LABELS[user.role]}</p>
            </div>
            <button
                type="button"
                onClick={handleLogout}
                disabled={signingOut}
                aria-label="Sign out"
                title="Sign out"
                className="flex size-9 shrink-0 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-destructive-soft hover:text-destructive focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40 disabled:opacity-60"
            >
                {signingOut ? <Spinner /> : <LogOutIcon className="size-4" />}
            </button>
        </div>
    )
}
