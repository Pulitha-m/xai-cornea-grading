/** Shared class strings for elements that are not the shadcn Button (router links, native submit buttons). */
export const primaryButton =
    "inline-flex h-10 items-center justify-center gap-2 rounded-full bg-primary px-5 text-sm font-semibold text-primary-foreground shadow-sm transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-70"

/** Data tables: tinted header row, hairline row separators, row hover. */
export const tableHead = "border-b border-border bg-sunken"

// Outer cells line up with the surrounding card's padding when the table bleeds to its edges.
const edgeCells = "first:pl-5 last:pr-5 sm:first:pl-6 sm:last:pr-6"

export const tableHeaderCell = `px-4 py-3 text-left text-2xs font-semibold tracking-wider whitespace-nowrap text-muted-foreground uppercase ${edgeCells}`

export const tableCell = `border-b border-muted px-4 py-3.5 align-middle ${edgeCells}`

export const tableRow = "transition-colors hover:bg-sunken"

export const textInput =
    "block h-10 w-full rounded-2xl border border-input bg-sunken px-3.5 text-sm text-foreground transition-colors placeholder:text-muted-foreground/70 focus:bg-card focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/25 disabled:opacity-60"

/** Boxed error message, matching the sign-in page. */
export const alertError =
    "rounded-2xl border border-destructive/25 bg-destructive-soft px-3.5 py-3 text-sm text-destructive"

/** Boxed caution message, e.g. when a result needs specialist review. */
export const alertWarning =
    "rounded-2xl border border-warning/25 bg-warning-soft px-3.5 py-3 text-sm text-warning"
