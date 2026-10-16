import { describe, expect, it } from "vitest"
import { parseEcd } from "@/lib/ecd"

describe("parseEcd", () => {
    it("treats blank as unavailable", () => {
        expect(parseEcd("  ")).toEqual({ ecd: null, error: null })
    })

    it("accepts values inside the API range, including the upper bound", () => {
        expect(parseEcd("2400")).toEqual({ ecd: 2400, error: null })
        expect(parseEcd("6000").ecd).toBe(6000)
    })

    it("rejects values outside the API range and non-numbers", () => {
        for (const value of ["0", "-5", "6000.5", "abc"]) {
            expect(parseEcd(value).error).not.toBeNull()
        }
    })
})
