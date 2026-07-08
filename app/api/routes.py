from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.graph.state import (
    DocumentsIndexRequest,
    DocumentsIndexResponse,
    InvokeRequest,
    InvokeResponse,
    RecommendationValidationRequest,
    RecommendationValidationResponse,
)


router = APIRouter(prefix="/api/auralys", tags=["auralys"])


def get_container(request: Request):
    return request.app.state.container


@router.get("/health")
def health(container=Depends(get_container)) -> dict:
    return container.healthcheck()


@router.post("/invoke", response_model=InvokeResponse)
def invoke(request: InvokeRequest, container=Depends(get_container)) -> InvokeResponse:
    return container.graph_service.invoke(request)


@router.post("/documents/index", response_model=DocumentsIndexResponse)
def index_documents(
    request: DocumentsIndexRequest,
    container=Depends(get_container),
) -> DocumentsIndexResponse:
    return container.index_documents(request)


@router.post(
    "/recommendations/validate",
    response_model=RecommendationValidationResponse,
)
def validate_recommendations(
    request: RecommendationValidationRequest,
    container=Depends(get_container),
) -> RecommendationValidationResponse:
    return container.validation_service.validate(request)
