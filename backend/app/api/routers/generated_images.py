from fastapi import APIRouter, HTTPException
from starlette.responses import FileResponse

from app.core.config import get_settings

router = APIRouter()

IMAGE_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


@router.get("/{filename}")
async def get_generated_image(filename: str) -> FileResponse:
    settings = get_settings()
    image_dir = settings.generated_images_dir
    if not image_dir.is_absolute():
        image_dir = settings.data_dir.parent / image_dir

    requested = (image_dir / filename).resolve()
    root = image_dir.resolve()
    if root not in requested.parents:
        raise HTTPException(status_code=404, detail="Image not found.")

    media_type = IMAGE_MEDIA_TYPES.get(requested.suffix.lower())
    if not media_type or not requested.exists() or not requested.is_file():
        raise HTTPException(status_code=404, detail="Image not found.")

    return FileResponse(requested, media_type=media_type)
