import type { ImageValidation } from "@/api/analysis"
import { alertWarning } from "@/lib/styles"

export function ImageValidationNote({ validation }: { validation: ImageValidation }) {
    if (validation.domainStatus === "UNVALIDATED_DEV_MODE") {
        return (
            <p role="alert" className={alertWarning}>
                Development mode: this image was not checked by the corneal-image validator. Do not rely on these
                results.
            </p>
        )
    }
    return (
        <p className="text-xs text-muted-foreground">
            Image accepted as a specular microscopy image of the corneal endothelium ({validation.width} ×{" "}
            {validation.height} px).
            {!validation.qualityAssessed && " Image quality and cell detail were not assessed automatically."}
        </p>
    )
}
