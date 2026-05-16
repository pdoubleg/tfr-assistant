from fastapi import APIRouter

from app.api.routers import batches, chat, evaluations, forms, generated_images, health, reviews

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(batches.router, prefix="/batches", tags=["batches"])
api_router.include_router(forms.router, prefix="/forms", tags=["forms"])
api_router.include_router(reviews.router, prefix="/reviews", tags=["reviews"])
api_router.include_router(evaluations.router, prefix="/evaluations", tags=["evaluations"])
api_router.include_router(
    generated_images.router,
    prefix="/generated-images",
    tags=["generated-images"],
)
