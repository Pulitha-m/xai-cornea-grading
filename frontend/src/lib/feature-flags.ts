/**
 * Parts of the app that are switched off for now. Set a flag back to true to restore the feature; its code
 * and tests are kept and run again automatically.
 */

/**
 * "Grafts from donor cases" on the Post-transplant follow-up page (the graft list from the transplant workflow).
 * Hidden temporarily, as agreed with the transplant workflow owner; the page shows only "Enter values by hand".
 */
export const SHOW_GRAFTS_ON_FOLLOWUP = false

/**
 * "Signed-off corneas in stock" on the Recipients & matching page (corneas from signed-off donor cases).
 * Hidden temporarily, as agreed with the transplant workflow owner; the page shows only "Enter corneas by hand".
 */
export const SHOW_STOCK_ON_MATCHING = false

/**
 * Follow-up risk (graft failure, ECD below 1000), the alert with next visit, and the what-if: built but still being
 * calibrated, so outside the current scope. Off: the follow-up result shows the ECD trajectory and its reasons only.
 */
export const SHOW_FOLLOWUP_RISK = false
