/**
 * The report's tissue ID ("NEB-2020-09-12673 L") in the form the app uses: the last five digits of the
 * tissue number and the eye side ("12673L"). Null when it cannot be derived (e.g. an OCR misread).
 */
export function reportTissueId(raw: string | null): string | null {
    const matches = [...(raw ?? "").toUpperCase().matchAll(/(\d{5})\D{0,3}([LR])(?![A-Z])/g)]
    const last = matches.at(-1)
    return last ? `${last[1]}${last[2]}` : null
}
