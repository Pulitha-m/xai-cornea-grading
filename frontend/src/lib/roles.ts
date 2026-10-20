import {
    ActivityIcon,
    BrainCircuitIcon,
    ClipboardListIcon,
    FileTextIcon,
    GaugeIcon,
    HexagonIcon,
    LayoutDashboardIcon,
    MicroscopeIcon,
    PackageIcon,
    ShieldCheckIcon,
    UsersIcon,
    type LucideIcon,
} from "lucide-react"
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

export const ANALYSIS_PATH = "/analysis"
export const CELLULAR_PATH = "/cellular"
export const DISEASE_PATH = "/disease"
export const GRADING_PATH = "/grading"

export function dashboardPathFor(role: Role): string {
    return DASHBOARD_PATHS[role]
}

export interface NavItem {
    label: string
    to: string
    icon: LucideIcon
    /** Visible only to these roles. */
    roles: Role[]
    /** Additionally requires this permission, if set. */
    permission?: Permission
}

/** Navigation shown in the app shell; filtered per user so hidden items are never rendered. */
export const NAV_ITEMS: NavItem[] = [
    { label: "Admin dashboard", to: DASHBOARD_PATHS.ADMIN, icon: LayoutDashboardIcon, roles: ["ADMIN"] },
    { label: "Manager dashboard", to: DASHBOARD_PATHS.MANAGER, icon: LayoutDashboardIcon, roles: ["MANAGER"] },
    { label: "Doctor dashboard", to: DASHBOARD_PATHS.DOCTOR, icon: LayoutDashboardIcon, roles: ["DOCTOR"] },
    { label: "Nurse dashboard", to: DASHBOARD_PATHS.NURSE, icon: LayoutDashboardIcon, roles: ["NURSE"] },
    { label: "Support dashboard", to: DASHBOARD_PATHS.SUPPORT_STAFF, icon: LayoutDashboardIcon, roles: ["SUPPORT_STAFF"] },
    {
        label: "AI analysis",
        to: ANALYSIS_PATH,
        icon: BrainCircuitIcon,
        roles: ["DOCTOR", "NURSE"],
        permission: "analysis:run",
    },
    {
        label: "Cellular analysis",
        to: CELLULAR_PATH,
        icon: HexagonIcon,
        roles: ["DOCTOR", "NURSE"],
        permission: "analysis:run",
    },
    {
        label: "Cornea grading",
        to: GRADING_PATH,
        icon: GaugeIcon,
        roles: ["DOCTOR", "NURSE"],
        permission: "analysis:run",
    },
    {
        label: "Disease screening",
        to: DISEASE_PATH,
        icon: MicroscopeIcon,
        roles: ["DOCTOR", "NURSE"],
        permission: "analysis:run",
    },
]

export interface PlannedModule extends NavItem {
    description: string
}

/**
 * Eye-bank modules from the NEBSL design that have no backend yet. They are listed in the
 * navigation and route to a "coming soon" screen; no sample data is shown for them.
 */
export const PLANNED_MODULES: PlannedModule[] = [
    {
        label: "Donor cases",
        to: "/cases",
        icon: ClipboardListIcon,
        roles: ["ADMIN", "MANAGER", "DOCTOR", "NURSE"],
        description: "Register donors, record clinical observations and track each cornea from collection to allocation.",
    },
    {
        label: "Tissue inventory",
        to: "/inventory",
        icon: PackageIcon,
        roles: ["ADMIN", "MANAGER", "NURSE", "SUPPORT_STAFF"],
        description: "Storage status, availability and inter-branch transfers of donor tissue.",
    },
    {
        label: "Recipients & matching",
        to: "/recipients",
        icon: UsersIcon,
        roles: ["ADMIN", "MANAGER", "DOCTOR", "NURSE"],
        description: "Waiting-list management and donor–recipient matching for clinical review.",
    },
    {
        label: "Post-transplant follow-up",
        to: "/post-transplant",
        icon: ActivityIcon,
        roles: ["ADMIN", "MANAGER", "DOCTOR", "NURSE"],
        description: "Graft monitoring with endothelial measurements recorded at scheduled follow-up visits.",
    },
    {
        label: "Reports",
        to: "/reports",
        icon: FileTextIcon,
        roles: ["ADMIN", "MANAGER", "DOCTOR"],
        description: "Clinical and operational reporting across cases and branches.",
    },
    {
        label: "Audit log",
        to: "/audit",
        icon: ShieldCheckIcon,
        roles: ["ADMIN"],
        description: "A searchable record of who did what, and when, across the system.",
    },
]

function canSee(user: User, item: NavItem): boolean {
    return item.roles.includes(user.role) && (item.permission === undefined || user.permissions.includes(item.permission))
}

export function visibleNavItems(user: User): NavItem[] {
    return NAV_ITEMS.filter((item) => canSee(user, item))
}

export function visiblePlannedModules(user: User): PlannedModule[] {
    return PLANNED_MODULES.filter((item) => canSee(user, item))
}
