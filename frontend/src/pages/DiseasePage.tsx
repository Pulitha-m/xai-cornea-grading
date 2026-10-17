import { MicroscopeIcon } from "lucide-react"
import { PageHeader } from "@/components/dashboard/PageHeader"
import { DiseasePanel } from "@/components/disease/DiseasePanel"

export function DiseasePage() {
    return (
        <>
            <PageHeader
                eyebrow={
                    <>
                        <MicroscopeIcon aria-hidden="true" />
                        AI intelligence
                    </>
                }
                title="Disease screening"
                description="Detects FECD, guttata, Descemet folds, polymegathism / pleomorphism and low cell density from a specular microscopy image and its CellChek values, grades the severity of each finding and shows Grad-CAM explanations. Research tool — not a medical diagnosis."
            />
            <DiseasePanel />
        </>
    )
}
