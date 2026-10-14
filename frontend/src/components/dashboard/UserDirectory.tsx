import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { UsersIcon } from "lucide-react"
import { assignRole, listUsers, setUserEnabled, USERS_QUERY_KEY } from "@/api/users"
import { useAuth } from "@/hooks/use-auth"
import { ROLE_LABELS } from "@/lib/roles"
import { alertError, tableCell, tableHead, tableHeaderCell, tableRow } from "@/lib/styles"
import { ROLES, type ManagedUser, type Role } from "@/types/auth"
import { EmptyState } from "@/components/ui/empty-state"
import { Spinner } from "@/components/ui/spinner"
import { StatusBadge } from "@/components/ui/status-badge"

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
            <p role="alert" className={alertError}>
                {users.error.message}
            </p>
        )
    }

    if (users.data.length === 0) {
        return <EmptyState icon={<UsersIcon />} title="No staff accounts yet" />
    }

    return (
        <div>
            {mutationError && (
                <p role="alert" className={`mb-4 ${alertError}`}>
                    {mutationError.message}
                </p>
            )}
            {/* Bleed to the card edges, as data tables do in the NEBSL design. */}
            <div className="-mx-5 -mb-5 overflow-x-auto sm:-mx-6 sm:-mb-6">
                <table className="w-full min-w-[40rem] text-sm [&_tbody_tr:last-child_td]:border-b-0">
                    <thead className={tableHead}>
                        <tr>
                            <th scope="col" className={tableHeaderCell}>Name</th>
                            <th scope="col" className={tableHeaderCell}>Username</th>
                            <th scope="col" className={tableHeaderCell}>Role</th>
                            <th scope="col" className={tableHeaderCell}>Status</th>
                            {canManageUsers && <th scope="col" className={tableHeaderCell}><span className="sr-only">Actions</span></th>}
                        </tr>
                    </thead>
                    <tbody>
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
        <tr className={tableRow}>
            <td className={tableCell}>
                <div className="font-medium">{user.fullName}</div>
                <div className="text-xs text-muted-foreground">{user.email}</div>
            </td>
            <td className={`${tableCell} text-muted-foreground`}>{user.username}</td>
            <td className={tableCell}>
                {canAssignRoles && !isSelf ? (
                    <select
                        aria-label={`Role for ${user.fullName}`}
                        value={user.role}
                        disabled={busy}
                        onChange={(e) => onRoleChange(e.target.value as Role)}
                        className="h-8 rounded-xl border border-input bg-sunken px-2.5 text-sm focus:bg-card focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/25"
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
            <td className={tableCell}>
                <StatusBadge tone={user.enabled ? "success" : "neutral"}>
                    {user.enabled ? "Active" : "Disabled"}
                </StatusBadge>
            </td>
            {canManageUsers && (
                <td className={`${tableCell} text-right`}>
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
