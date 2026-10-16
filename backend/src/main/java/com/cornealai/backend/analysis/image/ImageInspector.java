package com.cornealai.backend.analysis.image;

import com.cornealai.backend.analysis.AnalysisRejectedException;
import com.cornealai.backend.analysis.config.AnalysisProperties;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

import javax.imageio.ImageIO;
import javax.imageio.ImageReader;
import javax.imageio.stream.ImageInputStream;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.util.Arrays;
import java.util.Iterator;

/**
 * First-line checks on an upload before it is stored: size, real file signature
 * (not the extension or declared content type) and header dimensions. Pixels are
 * not decoded here, so oversized "decompression bomb" images are rejected cheaply.
 * ml-service decodes and validates the image fully before analysis.
 */
@Component
public class ImageInspector {

    private static final byte[] JPEG_MAGIC = {(byte) 0xFF, (byte) 0xD8, (byte) 0xFF};
    private static final byte[] PNG_MAGIC = {(byte) 0x89, 'P', 'N', 'G', '\r', '\n', 0x1A, '\n'};

    public record InspectedImage(String format, String contentType, String extension, int width, int height) {
    }

    private final AnalysisProperties.Images limits;

    public ImageInspector(AnalysisProperties properties) {
        this.limits = properties.images();
    }

    public InspectedImage inspect(byte[] data) {
        if (data == null || data.length == 0) {
            throw reject(HttpStatus.UNPROCESSABLE_CONTENT, "IMAGE_DECODE_FAILED", "The uploaded file is empty.");
        }
        if (data.length > limits.maxBytes()) {
            throw reject(HttpStatus.PAYLOAD_TOO_LARGE, "IMAGE_TOO_LARGE",
                    "Images must be at most " + limits.maxBytes() / (1024 * 1024) + " MB.");
        }

        String format;
        if (startsWith(data, JPEG_MAGIC)) {
            format = "jpeg";
        } else if (startsWith(data, PNG_MAGIC)) {
            format = "png";
        } else {
            throw reject(HttpStatus.UNSUPPORTED_MEDIA_TYPE, "UNSUPPORTED_IMAGE_FORMAT", "Upload a JPEG or PNG image.");
        }

        int width;
        int height;
        try (ImageInputStream stream = ImageIO.createImageInputStream(new ByteArrayInputStream(data))) {
            Iterator<ImageReader> readers = ImageIO.getImageReadersByFormatName(format);
            if (stream == null || !readers.hasNext()) {
                throw reject(HttpStatus.UNPROCESSABLE_CONTENT, "IMAGE_DECODE_FAILED", "The image could not be read.");
            }
            ImageReader reader = readers.next();
            try {
                reader.setInput(stream, true, true);
                width = reader.getWidth(0);
                height = reader.getHeight(0);
            } finally {
                reader.dispose();
            }
        } catch (IOException | RuntimeException e) {
            if (e instanceof AnalysisRejectedException rejected) {
                throw rejected;
            }
            throw reject(HttpStatus.UNPROCESSABLE_CONTENT, "IMAGE_DECODE_FAILED",
                    "The image could not be read. Upload an uncorrupted JPEG or PNG.");
        }

        if (Math.min(width, height) < limits.minSide() || Math.max(width, height) > limits.maxSide()
                || (long) width * height > limits.maxPixels()) {
            throw reject(HttpStatus.UNPROCESSABLE_CONTENT, "IMAGE_DIMENSIONS_INVALID",
                    "Image sides must be between " + limits.minSide() + " and " + limits.maxSide() + " pixels.");
        }

        return format.equals("jpeg")
                ? new InspectedImage(format, "image/jpeg", "jpg", width, height)
                : new InspectedImage(format, "image/png", "png", width, height);
    }

    private static boolean startsWith(byte[] data, byte[] prefix) {
        return data.length >= prefix.length && Arrays.equals(Arrays.copyOf(data, prefix.length), prefix);
    }

    private static AnalysisRejectedException reject(HttpStatus status, String code, String message) {
        return new AnalysisRejectedException(status, code, "file", message);
    }
}
