import { useId, useRef, useState, type FormEvent } from "react"
import { Navigate, useLocation, useNavigate, type Location } from "react-router-dom"
import { cn } from "cn"
import { useAuth } from "@/hooks/use-auth"
import { ApiError } from "@/lib/api-client"
import { dashboardPathFor } from "@/lib/roles"
import { BrandMark } from "@/components/brand/BrandMark"
import { AlertCircleIcon, EyeIcon, EyeOffIcon, ShieldIcon } from "@/components/ui/icons"
import { Spinner } from "@/components/ui/spinner"
import { FullPageSpinner } from "@/components/ui/spinner"

interface FieldErrors {
    identifier?: string
    password?: string
}

function validate(identifier: string, password: string): FieldErrors {
    const errors: FieldErrors = {}
    if (!identifier.trim()) {
        errors.identifier = "Enter your email or username."
    }
    if (!password) {
        errors.password = "Enter your password."
    }
    return errors
}

/** Where to go after login: the originally requested page, else the role's dashboard. */
function destinationAfterLogin(from: Location | undefined, fallback: string) {
    if (!from || from.pathname === "/login") {
        return fallback
    }
    return `${from.pathname}${from.search}${from.hash}`
}

export function LoginPage() {
    const { status, user, login, sessionExpired } = useAuth()
    const navigate = useNavigate()
    const location = useLocation()
    const from = (location.state as { from?: Location } | null)?.from

    const [identifier, setIdentifier] = useState("")
    const [password, setPassword] = useState("")
    const [rememberMe, setRememberMe] = useState(false)
    const [showPassword, setShowPassword] = useState(false)
    const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
    const [formError, setFormError] = useState<string | null>(null)
    const [submitting, setSubmitting] = useState(false)
    const [showRecoveryHelp, setShowRecoveryHelp] = useState(false)

    const identifierRef = useRef<HTMLInputElement>(null)
    const passwordRef = useRef<HTMLInputElement>(null)
    const ids = {
        identifier: useId(),
        identifierError: useId(),
        password: useId(),
        passwordError: useId(),
        remember: useId(),
        recovery: useId(),
    }

    if (status === "loading") {
        return <FullPageSpinner label="Checking your session" />
    }

    if (status === "authenticated" && user && !submitting) {
        return <Navigate to={dashboardPathFor(user.role)} replace />
    }

    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        setFormError(null)

        const errors = validate(identifier, password)
        setFieldErrors(errors)
        if (errors.identifier) {
            identifierRef.current?.focus()
            return
        }
        if (errors.password) {
            passwordRef.current?.focus()
            return
        }

        setSubmitting(true)
        try {
            const signedIn = await login({ identifier: identifier.trim(), password, rememberMe })
            navigate(destinationAfterLogin(from, dashboardPathFor(signedIn.role)), { replace: true })
        } catch (error) {
            // Server messages are already generic and safe; anything else gets a neutral fallback.
            setFormError(error instanceof ApiError ? error.message : "Unable to sign in. Please try again.")
            setPassword("")
            passwordRef.current?.focus()
            setSubmitting(false)
        }
    }

    const inputClass =
        "block h-11 w-full rounded-lg border bg-card px-3 text-sm text-foreground shadow-xs transition-colors placeholder:text-muted-foreground/70 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/25 disabled:opacity-60"

    return (
        <div className="flex min-h-svh bg-background">
            {/* Brand panel (large screens) */}
            <aside className="relative hidden w-[44%] max-w-xl flex-col justify-between overflow-hidden bg-primary p-12 text-white lg:flex">
                <BrandMark inverted />

                <div className="relative z-10 max-w-sm">
                    <h2 className="text-2xl font-semibold leading-snug tracking-tight">
                        Explainable corneal assessment for clinical teams.
                    </h2>
                    <p className="mt-3 text-sm leading-relaxed text-white/70">
                        Grade corneal tissue, review AI-assisted findings and coordinate care — with access tailored to
                        your role.
                    </p>
                </div>

                <p className="relative z-10 flex items-center gap-2 text-xs text-white/60">
                    <ShieldIcon className="size-4" />
                    Access is restricted to authorised personnel.
                </p>

                {/* Subtle iris motif */}
                <svg
                    viewBox="0 0 400 400"
                    className="pointer-events-none absolute -right-28 -bottom-28 size-[26rem] text-white/[0.06]"
                    aria-hidden="true"
                >
                    <circle cx="200" cy="200" r="190" fill="none" stroke="currentColor" strokeWidth="2" />
                    <circle cx="200" cy="200" r="130" fill="none" stroke="currentColor" strokeWidth="2" />
                    <circle cx="200" cy="200" r="70" fill="none" stroke="currentColor" strokeWidth="2" />
                    <circle cx="200" cy="200" r="28" fill="currentColor" />
                </svg>
            </aside>

            {/* Form */}
            <main className="flex flex-1 items-center justify-center px-4 py-12 sm:px-8">
                <div className="w-full max-w-sm">
                    <BrandMark className="mb-8 lg:hidden" />

                    <h1 className="text-2xl font-semibold tracking-tight text-foreground">Welcome back</h1>
                    <p className="mt-1.5 text-sm text-muted-foreground">Sign in to continue to your workspace.</p>

                    {sessionExpired && !formError && (
                        <div
                            role="status"
                            className="mt-6 rounded-lg border border-border bg-muted px-3.5 py-3 text-sm text-foreground"
                        >
                            Your session has expired. Please sign in again.
                        </div>
                    )}

                    {formError && (
                        <div
                            role="alert"
                            className="mt-6 flex gap-2.5 rounded-lg border border-destructive/25 bg-destructive-soft px-3.5 py-3 text-sm text-destructive"
                        >
                            <AlertCircleIcon className="mt-0.5 size-4 shrink-0" />
                            <span>{formError}</span>
                        </div>
                    )}

                    <form className="mt-6 space-y-5" onSubmit={handleSubmit} noValidate>
                        <div>
                            <label htmlFor={ids.identifier} className="mb-1.5 block text-sm font-medium">
                                Email or username
                            </label>
                            <input
                                ref={identifierRef}
                                id={ids.identifier}
                                name="identifier"
                                type="text"
                                autoComplete="username"
                                autoCapitalize="none"
                                spellCheck={false}
                                value={identifier}
                                onChange={(e) => {
                                    setIdentifier(e.target.value)
                                    if (fieldErrors.identifier) setFieldErrors((f) => ({ ...f, identifier: undefined }))
                                }}
                                disabled={submitting}
                                aria-invalid={fieldErrors.identifier ? true : undefined}
                                aria-describedby={fieldErrors.identifier ? ids.identifierError : undefined}
                                className={cn(inputClass, fieldErrors.identifier ? "border-destructive" : "border-input")}
                                placeholder="name@hospital.org"
                            />
                            {fieldErrors.identifier && (
                                <p id={ids.identifierError} className="mt-1.5 text-xs text-destructive">
                                    {fieldErrors.identifier}
                                </p>
                            )}
                        </div>

                        <div>
                            <div className="mb-1.5 flex items-center justify-between">
                                <label htmlFor={ids.password} className="block text-sm font-medium">
                                    Password
                                </label>
                                {/*
                                  Integration point: no self-service recovery exists yet (it needs a verified
                                  email channel). Replace this toggle with a link to the reset flow once the
                                  backend exposes one; until then administrators reset passwords via
                                  PUT /api/users/{id}/password.
                                */}
                                <button
                                    type="button"
                                    onClick={() => setShowRecoveryHelp((v) => !v)}
                                    aria-expanded={showRecoveryHelp}
                                    aria-controls={ids.recovery}
                                    className="rounded text-xs font-medium text-accent hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                                >
                                    Forgot password?
                                </button>
                            </div>
                            <div className="relative">
                                <input
                                    ref={passwordRef}
                                    id={ids.password}
                                    name="password"
                                    type={showPassword ? "text" : "password"}
                                    autoComplete="current-password"
                                    value={password}
                                    onChange={(e) => {
                                        setPassword(e.target.value)
                                        if (fieldErrors.password) setFieldErrors((f) => ({ ...f, password: undefined }))
                                    }}
                                    disabled={submitting}
                                    aria-invalid={fieldErrors.password ? true : undefined}
                                    aria-describedby={fieldErrors.password ? ids.passwordError : undefined}
                                    className={cn(
                                        inputClass,
                                        "pr-11",
                                        fieldErrors.password ? "border-destructive" : "border-input",
                                    )}
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowPassword((v) => !v)}
                                    aria-label={showPassword ? "Hide password" : "Show password"}
                                    aria-pressed={showPassword}
                                    className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-lg text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/25"
                                >
                                    {showPassword ? <EyeOffIcon className="size-4" /> : <EyeIcon className="size-4" />}
                                </button>
                            </div>
                            {fieldErrors.password && (
                                <p id={ids.passwordError} className="mt-1.5 text-xs text-destructive">
                                    {fieldErrors.password}
                                </p>
                            )}
                            {showRecoveryHelp && (
                                <p
                                    id={ids.recovery}
                                    className="mt-2 rounded-lg bg-accent-soft px-3 py-2.5 text-xs leading-relaxed text-foreground"
                                >
                                    For security, passwords are reset by your eye bank system administrator. Please contact
                                    them to regain access.
                                </p>
                            )}
                        </div>

                        <div className="flex items-center gap-2.5">
                            <input
                                id={ids.remember}
                                type="checkbox"
                                checked={rememberMe}
                                onChange={(e) => setRememberMe(e.target.checked)}
                                disabled={submitting}
                                className="size-4 rounded border-input accent-primary focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/25"
                            />
                            <label htmlFor={ids.remember} className="text-sm text-muted-foreground">
                                Keep me signed in on this device
                            </label>
                        </div>

                        <button
                            type="submit"
                            disabled={submitting}
                            className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-primary text-sm font-medium text-primary-foreground shadow-sm transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-70"
                        >
                            {submitting && <Spinner />}
                            {submitting ? "Signing in…" : "Sign in"}
                        </button>
                    </form>

                    <p className="mt-10 text-center text-xs text-muted-foreground">
                        Accounts are issued by your administrator.
                    </p>
                </div>
            </main>
        </div>
    )
}
