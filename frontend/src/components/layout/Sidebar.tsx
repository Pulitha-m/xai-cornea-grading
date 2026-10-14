import { NavLink } from "react-router-dom"
import { cn } from "cn"
import { useAuth } from "@/hooks/use-auth"
import { visibleNavItems, visiblePlannedModules, type NavItem } from "@/lib/roles"
import { BrandMark } from "@/components/brand/BrandMark"
import { AccountFooter } from "@/components/layout/AccountFooter"

/** Sidebar content shared by the desktop rail and the mobile drawer. */
export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
    const { user } = useAuth()

    if (!user) {
        return null
    }

    return (
        <div className="flex h-full w-full flex-col">
            <div className="flex shrink-0 items-center justify-center px-5 py-5">
                <BrandMark className="h-14" />
            </div>

            <nav aria-label="Main" className="flex-1 space-y-6 overflow-y-auto px-4 py-4">
                <NavSection title="Workspace" items={visibleNavItems(user)} onNavigate={onNavigate} />
                <NavSection title="Coming soon" items={visiblePlannedModules(user)} onNavigate={onNavigate} planned />
            </nav>

            <AccountFooter />
        </div>
    )
}

function NavSection({
    title,
    items,
    planned = false,
    onNavigate,
}: {
    title: string
    items: NavItem[]
    planned?: boolean
    onNavigate?: () => void
}) {
    if (items.length === 0) {
        return null
    }

    return (
        <div>
            <p className="px-3 pb-2 text-2xs font-bold tracking-wider text-muted-foreground uppercase">{title}</p>
            <ul className="space-y-1">
                {items.map((item) => (
                    <li key={item.to}>
                        <NavLink
                            to={item.to}
                            onClick={onNavigate}
                            className={({ isActive }) =>
                                cn(
                                    "flex items-center gap-3 rounded-2xl border px-3.5 py-2.5 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40",
                                    isActive
                                        ? "border-secondary bg-secondary text-secondary-foreground shadow-card"
                                        : "border-transparent text-muted-foreground hover:bg-muted hover:text-foreground",
                                )
                            }
                        >
                            {({ isActive }) => (
                                <>
                                    <item.icon
                                        className={cn("size-4 shrink-0", isActive ? "text-accent" : "text-muted-foreground/70")}
                                        aria-hidden="true"
                                    />
                                    <span className="min-w-0 flex-1 truncate">{item.label}</span>
                                    {planned && (
                                        <span className="rounded-full bg-highlight-soft px-1.5 py-0.5 text-[10px] font-semibold text-warning">
                                            Soon
                                        </span>
                                    )}
                                </>
                            )}
                        </NavLink>
                    </li>
                ))}
            </ul>
        </div>
    )
}
