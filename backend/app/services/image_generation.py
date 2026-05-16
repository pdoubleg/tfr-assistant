"""OpenAI image generation and local artifact persistence."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

import httpx
from openai import AsyncOpenAI

from app.core.config import Settings

ImageQuality = Literal["standard", "high", "auto", "low", "medium", "hd"]
ImageFormat = Literal["png", "jpeg", "webp"]
ImageBackground = Literal["auto", "transparent", "opaque"]


@dataclass(frozen=True, slots=True)
class GeneratedImage:
    id: str
    filename: str
    path: Path
    url: str
    mime_type: str
    prompt: str
    model: str
    size: str
    quality: str
    created_at: str
    revised_prompt: str | None = None


class ImageGenerationError(RuntimeError):
    """Raised when OpenAI returns no image payload that can be persisted."""


class ImageGenerationService:
    def __init__(
        self,
        settings: Settings,
        *,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self.settings = settings
        self.client = client or AsyncOpenAI()

    async def generate(
        self,
        *,
        prompt: str,
        model: str | None = None,
        size: str = "1536x864",
        quality: ImageQuality = "high",
        n: int = 1,
        output_format: ImageFormat = "png",
        background: ImageBackground = "auto",
    ) -> list[GeneratedImage]:
        if not prompt.strip():
            raise ImageGenerationError("Image prompt cannot be empty.")
        if n < 1 or n > 4:
            raise ImageGenerationError("Generate between 1 and 4 images per tool call.")

        selected_model = model or self.settings.image_model
        request_kwargs = {
            "model": selected_model,
            "prompt": prompt,
            "size": size,
            "quality": quality,
            "n": n,
            "output_format": output_format,
            "background": background,
        }
        if _supports_response_format(selected_model):
            request_kwargs["response_format"] = "b64_json"

        response = await self.client.images.generate(**request_kwargs)

        items = list(getattr(response, "data", []) or [])
        if not items:
            raise ImageGenerationError("OpenAI returned no image data.")

        image_dir = self.settings.generated_images_dir
        if not image_dir.is_absolute():
            image_dir = self.settings.data_dir.parent / image_dir
        image_dir.mkdir(parents=True, exist_ok=True)

        results: list[GeneratedImage] = []
        for index, item in enumerate(items, start=1):
            image_bytes = await _extract_image_bytes(item)
            image_id = str(uuid4())
            suffix = _file_suffix(output_format)
            filename = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{image_id}.{suffix}"
            path = image_dir / filename
            path.write_bytes(image_bytes)

            created_at = datetime.now(UTC).isoformat()
            revised_prompt = getattr(item, "revised_prompt", None)
            metadata = {
                "id": image_id,
                "filename": filename,
                "prompt": prompt,
                "revised_prompt": revised_prompt,
                "model": selected_model,
                "size": size,
                "quality": quality,
                "output_format": output_format,
                "background": background,
                "index": index,
                "created_at": created_at,
            }
            path.with_suffix(".json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            results.append(
                GeneratedImage(
                    id=image_id,
                    filename=filename,
                    path=path,
                    url=f"/api/generated-images/{filename}",
                    mime_type=_mime_type(output_format),
                    prompt=prompt,
                    model=selected_model,
                    size=size,
                    quality=quality,
                    created_at=created_at,
                    revised_prompt=revised_prompt,
                )
            )

        return results


async def _extract_image_bytes(item: object) -> bytes:
    b64_json = getattr(item, "b64_json", None)
    if isinstance(b64_json, str) and b64_json:
        return base64.b64decode(b64_json)

    url = getattr(item, "url", None)
    if isinstance(url, str) and url:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content

    raise ImageGenerationError("OpenAI image response did not include b64_json or url data.")


def _file_suffix(output_format: ImageFormat) -> str:
    return "jpg" if output_format == "jpeg" else output_format


def _mime_type(output_format: ImageFormat) -> str:
    if output_format == "jpeg":
        return "image/jpeg"
    return f"image/{output_format}"


def _supports_response_format(model: str) -> bool:
    return not model.startswith(("gpt-image", "chatgpt-image"))
