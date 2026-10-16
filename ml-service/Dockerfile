# ---------------------------------------------------------------------------
# Stage 1: regenerate both ONNX backbones from versioned sources and verify that
# each reproduces the reference output recorded when its model was trained
# (scripts/backbone_check.py; byte hashes vary across CPUs, so they are not
# compared). A mismatch fails the build. Each verified file gets a
# <file>.verified.json record that the service checks at load.
#   - domain validator: torchvision ResNet-18 IMAGENET1K_V1
#   - hybrid grading model: torchvision ResNet-50 IMAGENET1K_V2
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS backbone

RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
        torch==2.14.1 torchvision==0.29.1 \
    && pip install --no-cache-dir onnx==1.23.2 onnxruntime==1.31.0 numpy

WORKDIR /build
COPY scripts/backbone_check.py scripts/export_domain_backbone.py ./
COPY models/domain_validator/classifier.json ./
RUN python export_domain_backbone.py /out/resnet18_backbone.onnx --verify classifier.json

COPY scripts/export_grading_backbone.py ./
COPY models/grading_hybrid_rf.json ./
RUN python export_grading_backbone.py /out/resnet50_backbone.onnx --verify grading_hybrid_rf.json

# ---------------------------------------------------------------------------
# Stage 2: the service (no torch; inference uses onnxruntime)
# ---------------------------------------------------------------------------
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# Install the exact versions pinned in uv.lock (cached separately from source)
COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY pipelines ./pipelines
COPY models ./models
COPY --from=backbone /out/resnet18_backbone.onnx /out/resnet18_backbone.onnx.verified.json ./models/domain_validator/
COPY --from=backbone /out/resnet50_backbone.onnx /out/resnet50_backbone.onnx.verified.json ./models/grading_backbone/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
