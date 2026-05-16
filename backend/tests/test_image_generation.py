import base64
import json
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.services.image_generation import ImageGenerationError, ImageGenerationService


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeImagesClient:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] | None = None

    async def generate(self, **kwargs: object) -> SimpleNamespace:
        self.kwargs = kwargs
        encoded = base64.b64encode(b"fake-image-bytes").decode("ascii")
        return SimpleNamespace(data=[SimpleNamespace(b64_json=encoded, revised_prompt=None)])


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.images = FakeImagesClient()


@pytest.mark.anyio
async def test_image_generation_saves_base64_artifact(tmp_path) -> None:
    client = FakeOpenAIClient()
    settings = Settings(
        data_dir=tmp_path / "data",
        generated_images_dir=tmp_path / "data" / "generated_images",
        image_model="gpt-image-2",
    )
    service = ImageGenerationService(settings, client=client)

    images = await service.generate(
        prompt="A cinematic futuristic library",
        size="1536x864",
        quality="high",
        output_format="png",
    )

    assert client.images.kwargs is not None
    assert client.images.kwargs["model"] == "gpt-image-2"
    assert "response_format" not in client.images.kwargs
    assert client.images.kwargs["output_format"] == "png"
    assert len(images) == 1
    assert images[0].path.read_bytes() == b"fake-image-bytes"
    assert images[0].url == f"/api/generated-images/{images[0].filename}"

    metadata = json.loads(images[0].path.with_suffix(".json").read_text(encoding="utf-8"))
    assert metadata["prompt"] == "A cinematic futuristic library"
    assert metadata["size"] == "1536x864"


@pytest.mark.anyio
async def test_image_generation_rejects_empty_prompt(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        generated_images_dir=tmp_path / "data" / "generated_images",
    )
    service = ImageGenerationService(settings, client=FakeOpenAIClient())

    with pytest.raises(ImageGenerationError, match="cannot be empty"):
        await service.generate(prompt="")


@pytest.mark.anyio
async def test_image_generation_requests_base64_for_dalle_models(tmp_path) -> None:
    client = FakeOpenAIClient()
    settings = Settings(
        data_dir=tmp_path / "data",
        generated_images_dir=tmp_path / "data" / "generated_images",
    )
    service = ImageGenerationService(settings, client=client)

    await service.generate(prompt="A clean product photo", model="dall-e-3")

    assert client.images.kwargs is not None
    assert client.images.kwargs["response_format"] == "b64_json"
