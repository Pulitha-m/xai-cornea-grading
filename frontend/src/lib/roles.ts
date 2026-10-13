import type { Permission, Role, User } from "@/types/auth"

export const ROLE_LABELS: Record<Role, string> = {
    ADMIN: "Administrator",
    MANAGER: "Manager",
    DOCTOR: "Doctor",
    NURSE: "Nurse",
    SUPPORT_STAFF: "Support Staff",
}

export const DASHBOARD_PATHS: Record<Role, string> = {
    ADMIN: "/admin/dashboard",
    MANAGER: "/manager/dashboard",
    DOCTOR: "/doctor/dashboard",
    NURSE: "/nurse/dashboard",
    SUPPORT_STAFF: "/support/dashboard",
}

export function dashboardPathFor(role: Role): string {
    return DASHBOARD_PATHS[role]
}

export interface NavItem {
    label: string
    to: string
    /** Visible only to these roles. */
    roles: Role[]
    /** Additionally requires this permission, if set. */
    permission?: Permission
}

/** Navigation shown in the app shell; filtered per user so hidden items are never rendered. */
export const NAV_ITEMS: NavItem[] = [
    { label: "Admin dashboard", to: DASHBOARD_PATHS.ADMIN, roles: ["ADMIN"] },
    { label: "Manager dashboard", to: DASHBOARD_PATHS.MANAGER, roles: ["MANAGER"] },
    { label: "Doctor dashboard", to: DASHBOARD_PATHS.DOCTOR, roles: ["DOCTOR"] },
    { label: "Nurse dashboard", to: DASHBOARD_PATHS.NURSE, roles: ["NURSE"] },
    { label: "Support dashboard", to: DASHBOARD_PATHS.SUPPORT_STAFF, roles: ["SUPPORT_STAFF"] },
]

export function visibleNavItems(user: User): NavItem[] {
    return NAV_ITEMS.filter(
        (item) =>
            item.roles.includes(user.role) &&
            (item.permission === undefined || user.permissions.includes(item.permission)),
    )
}
