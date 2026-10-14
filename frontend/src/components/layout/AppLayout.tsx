import { useCallback, useEffect, useRef, useState } from "react"
import { Outlet } from "react-router-dom"
import { XIcon } from "lucide-react"
import { useAuth } from "@/hooks/use-auth"
import { Sidebar } from "@/components/layout/Sidebar"
import { TopBar } from "@/components/layout/TopBar"

/** Shared shell for every signed-in page: sidebar (drawer on small screens), top bar, content. */
export function AppLayout() {
    const { user } = useAuth()
    const [navOpen, setNavOpen] = useState(false)
    const menuButtonRef = useRef<HTMLButtonElement>(null)

    const closeNav = useCallback(() => {
        setNavOpen(false)
        menuButtonRef.current?.focus()
    }, [])

    useEffect(() => {
        if (!navOpen) {
            return
        }
        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key === "Escape") {
                closeNav()
            }
        }
        document.addEventListener("keydown", onKeyDown)
        return () => document.removeEventListener("keydown", onKeyDown)
    }, [navOpen, closeNav])

    if (!user) {
        return null
    }

    return (
        <div className="flex min-h-svh bg-background">
            <aside className="sticky top-0 hidden h-svh w-64 shrink-0 border-r border-border bg-card lg:flex">
                <Sidebar />
            </aside>

            {navOpen && (
                <div id="mobile-navigation" role="dialog" aria-modal="true" aria-label="Navigation" className="fixed inset-0 z-40 lg:hidden">
                    <button
                        type="button"
                        tabIndex={-1}
                        aria-label="Close navigation"
                        onClick={closeNav}
                        className="absolute inset-0 bg-foreground/30"
                    />
                    <div className="relative flex h-full w-72 max-w-[85vw] bg-card shadow-pop">
                        <button
                            type="button"
                            autoFocus
                            onClick={closeNav}
                            aria-label="Close navigation"
                            className="absolute top-3 right-3 z-10 flex size-8 items-center justify-center rounded-xl text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
                        >
                            <XIcon className="size-4" aria-hidden="true" />
                        </button>
                        <Sidebar onNavigate={() => setNavOpen(false)} />
                    </div>
                </div>
            )}

            <div className="flex min-w-0 flex-1 flex-col">
                <TopBar navOpen={navOpen} onOpenNav={() => setNavOpen(true)} menuButtonRef={menuButtonRef} />
                <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
                    <Outlet />
                </main>
            </div>
        </div>
    )
}
