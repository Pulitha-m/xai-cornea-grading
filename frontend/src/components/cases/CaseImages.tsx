import { useEffect, useId, useMemo, useState, type ChangeEvent } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { IMAGE_ACCEPT, IMAGE_MAX_BYTES } from "@/api/analysis"
import { fetchCaseImage, uploadCaseImage, type CaseImage } from "@/api/cases"
import { Card } from "@/components/dashboard/PageHeader"
import { EmptyState } from "@/components/ui/empty-state"
import { Spinner } from "@/components/ui/spinner"
import { checkImageFile } from "@/lib/image-file"
import { alertError, textInput } from "@/lib/styles"

/** The case's specular microscopy images: stored encrypted, shown here decrypted by the server. */
export function CaseImages({ caseId, images }: { caseId: string; images: CaseImage[] }) {
    const queryClient = useQueryClient()
    const [fileError, setFileError] = useState<string | null>(null)
    const [progress, setProgress] = useState(0)
    const inputId = useId()
    const helpId = useId()

    const upload = useMutation({
        mutationFn: (file: File) => uploadCaseImage(caseId, file, setProgress),
        onSuccess: () => {
            void queryClient.invalidateQueries({ queryKey: ["case", caseId] })
            void queryClient.invalidateQueries({ queryKey: ["case", caseId, "images"] })
        },
    })

    async function handleFile(event: ChangeEvent<HTMLInputElement>) {
        const file = event.target.files?.[0]
        event.target.value = ""
        upload.reset()
        if (!file) return
        const error = await checkImageFile(file)
        setFileError(error)
        if (error === null) {
            setProgress(0)
            upload.mutate(file)
        }
    }

    const shownError = fileError ?? (upload.isError ? upload.error.message : null)

    return (
        <Card title="Images" description="Specular microscopy images of this cornea. Each is stored encrypted and can be analysed any number of times.">
            <div className="space-y-4">
                <div>
                    <label htmlFor={inputId} className="mb-1.5 block text-sm font-medium">Add an image</label>
                    <input id={inputId} type="file" accept={IMAGE_ACCEPT} onChange={handleFile} disabled={upload.isPending}
                        aria-describedby={helpId} className={`${textInput} py-2`} />
                    <p id={helpId} className="mt-1.5 text-xs text-muted-foreground">
                        JPEG or PNG, up to {IMAGE_MAX_BYTES / (1024 * 1024)} MB, as exported by the specular microscope.
                    </p>
                </div>
                {upload.isPending && (
                    <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Spinner /> Uploading… {Math.round(progress * 100)} %
                    </p>
                )}
                {shownError && <p role="alert" className={alertError}>{shownError}</p>}

                {images.length === 0 ? (
                    <EmptyState title="No images yet" description="Add the specular microscopy image to analyse this cornea." />
                ) : (
                    <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                        {images.map((image, index) => (
                            <li key={image.id} className="overflow-hidden rounded-2xl border border-border bg-sunken">
                                <CaseImageView caseId={caseId} image={image} alt={`Image ${images.length - index}`} />
                                <p className="px-3 py-2 text-xs text-muted-foreground">
                                    Image {images.length - index} · {image.width}×{image.height} · {new Date(image.uploadedAt).toLocaleString("en-GB")}
                                </p>
                            </li>
                        ))}
                    </ul>
                )}
            </div>
        </Card>
    )
}

/** Fetches the decrypted image with the session token and shows it through a short-lived object URL. */
export function CaseImageView({ caseId, image, alt }: { caseId: string; image: CaseImage; alt: string }) {
    const blob = useQuery({
        queryKey: ["case", caseId, "image", image.id],
        queryFn: () => fetchCaseImage(caseId, image.id),
        staleTime: Infinity,
        gcTime: 60_000,
    })
    const url = useMemo(
        () => (blob.data && typeof URL.createObjectURL === "function" ? URL.createObjectURL(blob.data) : null),
        [blob.data],
    )
    useEffect(() => () => {
        if (url) URL.revokeObjectURL(url)
    }, [url])

    if (blob.isError) return <p className="p-3 text-xs text-destructive">The image could not be loaded.</p>
    if (!url) return <div className="flex h-40 items-center justify-center"><Spinner /></div>
    return <img src={url} alt={alt} className="h-40 w-full object-contain" />
}
