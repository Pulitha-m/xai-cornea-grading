import { IMAGE_MAX_BYTES, IMAGE_MAX_SIDE, IMAGE_MIN_SIDE } from "@/api/analysis"

const JPEG = [0xff, 0xd8, 0xff]
const PNG = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]

function readHeader(file: File, length: number): Promise<Uint8Array> {
    return new Promise((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer))
        reader.onerror = () => reject(reader.error)
        reader.readAsArrayBuffer(file.slice(0, length))
    })
}

function startsWith(bytes: Uint8Array, signature: number[]) {
    return signature.every((value, i) => bytes[i] === value)
}

/**
 * Immediate feedback before upload: empty files, size, the real file signature (not the
 * extension) and, where the browser can decode it, the image dimensions. This is a
 * convenience only; the server applies the same checks and the corneal-image validation.
 */
export async function checkImageFile(file: File): Promise<string | null> {
    if (file.size === 0) {
        return "The selected file is empty."
    }
    if (file.size > IMAGE_MAX_BYTES) {
        return `Images must be at most ${IMAGE_MAX_BYTES / (1024 * 1024)} MB.`
    }

    let header: Uint8Array
    try {
        header = await readHeader(file, PNG.length)
    } catch {
        return "The selected file could not be read."
    }
    if (!startsWith(header, JPEG) && !startsWith(header, PNG)) {
        return "Choose a JPEG or PNG image."
    }

    if (typeof createImageBitmap === "function") {
        try {
            const bitmap = await createImageBitmap(file)
            const { width, height } = bitmap
            bitmap.close()
            if (Math.min(width, height) < IMAGE_MIN_SIDE || Math.max(width, height) > IMAGE_MAX_SIDE) {
                return `Image sides must be between ${IMAGE_MIN_SIDE} and ${IMAGE_MAX_SIDE} pixels.`
            }
        } catch {
            return "The image could not be decoded. Choose an uncorrupted JPEG or PNG."
        }
    }
    return null
}
