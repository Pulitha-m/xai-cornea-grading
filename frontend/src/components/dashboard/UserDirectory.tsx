import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { cn } from "cn"
import { assignRole, listUsers, setUserEnabled, USERS_QUERY_KEY } from "@/api/users"
import { useAuth } from "@/hooks/use-auth"
import { ROLE_LABELS } from "@/lib/roles"
import { ROLES, type ManagedUser, type Role } from "@/types/auth"
import { Spinner } from "@/components/ui/spinner"

/**
 * Staff list. Read-only unless the user may assign roles / manage accounts;
 * controls are hidden otherwise, and the API rejects such calls regardless.
 */
export function UserDirectory() {
    const { user: currentUser, hasPermission } = useAuth()
    const canAssignRoles = hasPermission("roles:assign")
    const canManageUsers = hasPermission("users:manage")
    const queryClient = useQueryClient()

    const users = useQuery({ queryKey: USERS_QUERY_KEY, queryFn: listUsers })

    const roleMutation = useMutation({
        mutationFn: ({ id, role }: { id: number; role: Role }) => assignRole(id, role),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: USERS_QUERY_KEY }),
    })

    const statusMutation = useMutation({
        mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) => setUserEnabled(id, enabled),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: USERS_QUERY_KEY }),
    })

    const mutationError = roleMutation.error ?? statusMutation.error

    if (users.isPending) {
        return (
            <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground" role="status">
                <Spinner /> Loading staff…
            </div>
        )
    }

    if (users.isError) {
        return (
            <p role="alert" className="py-6 text-sm text-destructive">
                {users.error.message}
            </p>
        )
    }

    return (
        <div>
            {mutationError && (
                <p role="alert" className="mb-3 text-sm text-destructive">
                    {mutationError.message}
                </p>
            )}
            <div className="overflow-x-auto">
                <table className="w-full min-w-[40rem] text-left text-sm">
                    <thead className="border-b border-border text-xs tracking-wide text-muted-foreground uppercase">
                        <tr>
                            <th scope="col" className="py-2.5 pr-4 font-medium">Name</th>
                            <th scope="col" className="py-2.5 pr-4 font-medium">Username</th>
                            <th scope="col" className="py-2.5 pr-4 font-medium">Role</th>
                            <th scope="col" className="py-2.5 pr-4 font-medium">Status</th>
                            {canManageUsers && <th scope="col" className="py-2.5 font-medium"><span className="sr-only">Actions</span></th>}
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                        {users.data.map((u) => (
                            <UserRow
                                key={u.id}
                                user={u}
                                isSelf={u.id === currentUser?.id}
                                canAssignRoles={canAssignRoles}
                                canManageUsers={canManageUsers}
                                onRoleChange={(role) => roleMutation.mutate({ id: u.id, role })}
                                onToggleEnabled={() => statusMutation.mutate({ id: u.id, enabled: !u.enabled })}
                                busy={roleMutation.isPending || statusMutation.isPending}
                            />
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    )
}

function UserRow({
    user,
    isSelf,
    canAssignRoles,
    canManageUsers,
    onRoleChange,
    onToggleEnabled,
    busy,
}: {
    user: ManagedUser
    isSelf: boolean
    canAssignRoles: boolean
    canManageUsers: boolean
    onRoleChange: (role: Role) => void
    onToggleEnabled: () => void
    busy: boolean
}) {
    return (
        <tr>
            <td className="py-3 pr-4">
                <div className="font-medium">{user.fullName}</div>
                <div className="text-xs text-muted-foreground">{user.email}</div>
            </td>
            <td className="py-3 pr-4 text-muted-foreground">{user.username}</td>
            <td className="py-3 pr-4">
                {canAssignRoles && !isSelf ? (
                    <select
                        aria-label={`Role for ${user.fullName}`}
                        value={user.role}
                        disabled={busy}
                        onChange={(e) => onRoleChange(e.target.value as Role)}
                        className="h-8 rounded-md border border-input bg-card px-2 text-sm focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/25"
                    >
                        {ROLES.map((role) => (
                            <option key={role} value={role}>
                                {ROLE_LABELS[role]}
                            </option>
                        ))}
                    </select>
                ) : (
                    ROLE_LABELS[user.role]
                )}
            </td>
            <td className="py-3 pr-4">
                <span
                    className={cn(
                        "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
                        user.enabled ? "bg-accent-soft text-accent" : "bg-muted text-muted-foreground",
                    )}
                >
                    {user.enabled ? "Active" : "Disabled"}
                </span>
            </td>
            {canManageUsers && (
                <td className="py-3 text-right">
                    {!isSelf && (
                        <button
                            type="button"
                            onClick={onToggleEnabled}
                            disabled={busy}
                            className="rounded-md px-2 py-1 text-xs font-medium text-primary hover:bg-muted focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/25 disabled:opacity-60"
                        >
                            {user.enabled ? "Disable" : "Enable"}
                        </button>
                    )}
                </td>
            )}
        </tr>
    )
}
