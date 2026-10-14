import { useId, useRef, useState, type FormEvent } from "react"
import { Navigate, useLocation, useNavigate, type Location } from "react-router-dom"
import { cn } from "cn"
import { useAuth } from "@/hooks/use-auth"
import { ApiError } from "@/lib/api-client"
import { dashboardPathFor } from "@/lib/roles"
import { ActivityIcon, ArrowRightIcon } from "lucide-react"
import { BRAND_NAME, BrandMark } from "@/components/brand/BrandMark"
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
        "block h-11 w-full rounded-2xl border bg-sunken px-4 text-sm text-foreground transition-colors placeholder:text-muted-foreground/70 focus:bg-card focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/25 disabled:opacity-60"

    return (
        <div className="relative flex min-h-svh items-center justify-center overflow-hidden bg-background px-4 py-8 sm:p-8">
            {/* Ambient glows */}
            <div aria-hidden="true" className="pointer-events-none absolute -top-32 -left-32 size-[30rem] rounded-full bg-sky-200/40 blur-3xl" />
            <div aria-hidden="true" className="pointer-events-none absolute -right-32 -bottom-32 size-[30rem] rounded-full bg-highlight/20 blur-3xl" />

            <div className="relative z-10 grid w-full max-w-4xl overflow-hidden rounded-3xl border border-border bg-card shadow-bento lg:grid-cols-12">
                {/* Brand panel (large screens) */}
                <aside className="relative hidden flex-col justify-between gap-8 overflow-hidden bg-foreground p-8 text-white lg:col-span-5 lg:flex">
                    <div
                        aria-hidden="true"
                        className="absolute inset-0 bg-cover bg-center opacity-40"
                        style={{ backgroundImage: "url('/login-background.jpg')" }}
                    />
                    <div aria-hidden="true" className="absolute inset-0 bg-linear-to-t from-foreground via-foreground/70 to-primary/40" />

                    <BrandMark inverted className="relative z-10 self-start" />

                    <div className="relative z-10">
                        <span className="mb-4 inline-flex items-center gap-1.5 rounded-full border border-sky-400/30 bg-sky-500/20 px-3 py-1 text-2xs font-bold tracking-wider text-sky-300 uppercase">
                            <ActivityIcon className="size-3.5" aria-hidden="true" />
                            Clinical decision support
                        </span>
                        <h2 className="text-2xl leading-tight font-bold tracking-tight">
                            Precision corneal evaluation &amp; graft intelligence
                        </h2>
                        <p className="mt-3 text-xs leading-relaxed text-white/70">
                            AI-assisted endothelial analysis, cornea grading and disease screening — with explanations
                            clinicians can review before any decision is made.
                        </p>
                    </div>

                    <p className="relative z-10 flex items-center gap-2 border-t border-white/10 pt-4 text-2xs font-semibold text-white/60">
                        <ShieldIcon className="size-4" />
                        Access is restricted to authorised personnel.
                    </p>
                </aside>

                {/* Form */}
                <main className="px-6 py-10 sm:px-10 lg:col-span-7">
                    <div className="mx-auto w-full max-w-sm">
                        <BrandMark className="mb-6 lg:hidden" />

                        <p className="text-2xs font-bold tracking-wider text-accent uppercase">{BRAND_NAME}</p>
                        <h1 className="mt-1 text-2xl font-bold tracking-tight text-foreground">Welcome back</h1>
                        <p className="mt-1.5 text-sm text-muted-foreground">Sign in to continue to your workspace.</p>

                        {sessionExpired && !formError && (
                            <div
                                role="status"
                                className="mt-6 rounded-2xl border border-border bg-muted px-3.5 py-3 text-sm text-foreground"
                            >
                                Your session has expired. Please sign in again.
                            </div>
                        )}

                        {formError && (
                            <div
                                role="alert"
                                className="mt-6 flex gap-2.5 rounded-2xl border border-destructive/25 bg-destructive-soft px-3.5 py-3 text-sm text-destructive"
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
                                        className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-2xl text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/25"
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
                                        className="mt-2 rounded-2xl bg-accent-soft px-3 py-2.5 text-xs leading-relaxed text-foreground"
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
                                className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-full bg-primary text-sm font-semibold text-primary-foreground shadow-sm transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-70"
                            >
                                {submitting && <Spinner />}
                                {submitting ? "Signing in…" : "Sign in"}
                                {!submitting && <ArrowRightIcon className="size-4" aria-hidden="true" />}
                            </button>
                        </form>

                        <p className="mt-8 text-center text-xs text-muted-foreground">
                            Accounts are issued by your administrator.
                        </p>
                    </div>
                </main>
            </div>
        </div>
    )
}
