from fastapi import APIRouter

from app.api.routers import (
    batches,
    chat,
    datasets,
    evaluations,
    forms,
    health,
    observability,
    optimizations,
    prompts,
    reviews,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(batches.router, prefix="/batches", tags=["batches"])
api_router.include_router(forms.router, prefix="/forms", tags=["forms"])
api_router.include_router(datasets.router, prefix="/datasets", tags=["datasets"])
api_router.include_router(prompts.router, prefix="/prompts", tags=["prompts"])
api_router.include_router(reviews.router, prefix="/reviews", tags=["reviews"])
api_router.include_router(evaluations.router, prefix="/evaluations", tags=["evaluations"])
api_router.include_router(optimizations.router, prefix="/optimizations", tags=["optimizations"])
api_router.include_router(observability.router, prefix="/observability", tags=["observability"])
