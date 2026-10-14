import { useId, useState, type FormEvent } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { createUser, USERS_QUERY_KEY } from "@/api/users"
import { ApiError } from "@/lib/api-client"
import { ROLE_LABELS } from "@/lib/roles"
import { primaryButton, textInput } from "@/lib/styles"
import { ROLES, type CreateUserRequest, type Role } from "@/types/auth"
import { Spinner } from "@/components/ui/spinner"

const EMPTY: CreateUserRequest = { username: "", email: "", fullName: "", role: "NURSE", password: "" }

/** Administrator-only account creation. The backend validates and enforces the permission. */
export function CreateUserForm() {
    const queryClient = useQueryClient()
    const [form, setForm] = useState<CreateUserRequest>(EMPTY)
    const [created, setCreated] = useState<string | null>(null)
    const id = useId()

    const mutation = useMutation({
        mutationFn: createUser,
        onSuccess: (user) => {
            setCreated(user.username)
            setForm(EMPTY)
            queryClient.invalidateQueries({ queryKey: USERS_QUERY_KEY })
        },
    })

    const fieldErrors = mutation.error instanceof ApiError ? mutation.error.fieldErrors : {}

    function update<K extends keyof CreateUserRequest>(key: K, value: CreateUserRequest[K]) {
        setForm((f) => ({ ...f, [key]: value }))
    }

    function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        setCreated(null)
        mutation.mutate(form)
    }

    const field = (key: keyof CreateUserRequest, label: string, input: React.ReactNode) => (
        <div>
            <label htmlFor={`${id}-${key}`} className="mb-1.5 block text-sm font-medium">
                {label}
            </label>
            {input}
            {fieldErrors[key] && (
                <p id={`${id}-${key}-error`} className="mt-1 text-xs text-destructive">
                    {fieldErrors[key]}
                </p>
            )}
        </div>
    )

    const inputProps = (key: keyof CreateUserRequest) => ({
        id: `${id}-${key}`,
        "aria-invalid": fieldErrors[key] ? true : undefined,
        "aria-describedby": fieldErrors[key] ? `${id}-${key}-error` : undefined,
        disabled: mutation.isPending,
        className: textInput,
    })

    return (
        <form className="grid gap-4 sm:grid-cols-2" onSubmit={handleSubmit} noValidate>
            {field("fullName", "Full name",
                <input {...inputProps("fullName")} value={form.fullName} onChange={(e) => update("fullName", e.target.value)} autoComplete="off" />)}
            {field("username", "Username",
                <input {...inputProps("username")} value={form.username} onChange={(e) => update("username", e.target.value)} autoComplete="off" />)}
            {field("email", "Email",
                <input {...inputProps("email")} type="email" value={form.email} onChange={(e) => update("email", e.target.value)} autoComplete="off" />)}
            {field("role", "Role",
                <select {...inputProps("role")} value={form.role} onChange={(e) => update("role", e.target.value as Role)}>
                    {ROLES.map((role) => (
                        <option key={role} value={role}>{ROLE_LABELS[role]}</option>
                    ))}
                </select>)}
            <div className="sm:col-span-2">
                {field("password", "Temporary password (12–72 characters)",
                    <input {...inputProps("password")} type="password" value={form.password} onChange={(e) => update("password", e.target.value)} autoComplete="new-password" />)}
            </div>

            <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
                <button
                    type="submit"
                    disabled={mutation.isPending}
                    className={primaryButton}
                >
                    {mutation.isPending && <Spinner />}
                    Create account
                </button>
                {mutation.isError && Object.keys(fieldErrors).length === 0 && (
                    <p role="alert" className="text-sm text-destructive">{mutation.error.message}</p>
                )}
                {created && (
                    <p role="status" className="text-sm text-accent">Account “{created}” created.</p>
                )}
            </div>
        </form>
    )
}
