from fastapi import FastAPI
from pipelines.cellular.service import run_cellular_analysis
from pipelines.grading.service import run_grading_analysis
from pipelines.disease.service import run_disease_analysis
from pipelines.recommendation.service import run_recommendation_analysis

from app.schemas.analysis import (
    AnalyzeRequest,
    AnalyzeResponse,
    CellularResult,
    DiseaseResult,
    GradingResult,
    RecommendationResult,
)

app = FastAPI(
    title="Corneal-AI ML Service",
    description="Machine learning inference service for Corneal-AI",
    version="0.1.0",
)


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "ml-service",
    }


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest):

    # Cellular
    try:
        cellular_data = run_cellular_analysis(request.image_url)

        cellular = CellularResult(
            status="completed",
            **cellular_data,
        )
    except Exception as e:
        cellular = CellularResult(
            status="failed",
            error=str(e),
        )

    # Grading
    try:
        grading_data = run_grading_analysis(request.image_url)

        grading = GradingResult(
            status="completed",
            **grading_data,
        )
    except Exception as e:
        grading = GradingResult(
            status="failed",
            error=str(e),
        )

    # Disease
    try:
        disease_data = run_disease_analysis(request.image_url)

        disease = DiseaseResult(
            status="completed",
            **disease_data,
        )
    except Exception as e:
        disease = DiseaseResult(
            status="failed",
            error=str(e),
        )

    # Recommendation
    try:
        recommendation_data = run_recommendation_analysis(
            request.image_url
        )

        recommendation = RecommendationResult(
            status="completed",
            **recommendation_data,
        )
    except Exception as e:
        recommendation = RecommendationResult(
            status="failed",
            error=str(e),
        )

    return AnalyzeResponse(
        case_id=request.case_id,
        status="completed",
        cellular=cellular,
        grading=grading,
        disease=disease,
        recommendation=recommendation,
    )