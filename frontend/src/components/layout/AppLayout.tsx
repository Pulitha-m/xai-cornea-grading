import { useState } from "react"
import { NavLink, Outlet, useNavigate } from "react-router-dom"
import { cn } from "cn"
import { useAuth } from "@/hooks/use-auth"
import { ROLE_LABELS, visibleNavItems } from "@/lib/roles"
import { BrandMark } from "@/components/brand/BrandMark"
import { LogOutIcon } from "@/components/ui/icons"
import { Spinner } from "@/components/ui/spinner"

/** Shared shell for every signed-in page: header, role-filtered navigation, content. */
export function AppLayout() {
    const { user, logout } = useAuth()
    const navigate = useNavigate()
    const [signingOut, setSigningOut] = useState(false)

    if (!user) {
        return null
    }

    const navItems = visibleNavItems(user)

    async function handleLogout() {
        setSigningOut(true)
        await logout()
        navigate("/login", { replace: true })
    }

    return (
        <div className="min-h-svh bg-background">
            <header className="border-b border-border bg-card">
                <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
                    <BrandMark />

                    <div className="flex items-center gap-3 sm:gap-4">
                        <div className="hidden text-right sm:block">
                            <p className="text-sm font-medium leading-tight">{user.fullName}</p>
                            <p className="text-xs text-muted-foreground">{ROLE_LABELS[user.role]}</p>
                        </div>
                        <button
                            type="button"
                            onClick={handleLogout}
                            disabled={signingOut}
                            className="inline-flex h-9 items-center gap-2 rounded-lg border border-border px-3 text-sm font-medium text-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40 disabled:opacity-60"
                        >
                            {signingOut ? <Spinner /> : <LogOutIcon className="size-4" />}
                            Sign out
                        </button>
                    </div>
                </div>

                {navItems.length > 0 && (
                    <nav aria-label="Main" className="mx-auto max-w-6xl px-4 sm:px-6">
                        <ul className="-mb-px flex gap-6 overflow-x-auto">
                            {navItems.map((item) => (
                                <li key={item.to}>
                                    <NavLink
                                        to={item.to}
                                        className={({ isActive }) =>
                                            cn(
                                                "inline-block border-b-2 py-3 text-sm font-medium whitespace-nowrap transition-colors focus-visible:outline-none focus-visible:text-accent",
                                                isActive
                                                    ? "border-accent text-primary"
                                                    : "border-transparent text-muted-foreground hover:text-foreground",
                                            )
                                        }
                                    >
                                        {item.label}
                                    </NavLink>
                                </li>
                            ))}
                        </ul>
                    </nav>
                )}
            </header>

            <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
                <Outlet />
            </main>
        </div>
    )
}
