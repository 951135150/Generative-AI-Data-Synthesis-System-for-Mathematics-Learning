from types import SimpleNamespace

import pytest

from src.ocr import OCRClient, OCRConfigurationError, OCRTranscriptionError


class FakeCompletions:
    def __init__(self, *, content="", error=None):
        self.content = content
        self.error = error
        self.last_request = None

    def create(self, **kwargs):
        self.last_request = kwargs
        if self.error:
            raise self.error
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


class FakeVisionClient:
    def __init__(self, completions):
        self.chat = SimpleNamespace(completions=completions)


def test_vision_ocr_requires_dedicated_configuration():
    client = OCRClient(api_key="", base_url="", model="")

    with pytest.raises(OCRConfigurationError):
        client.transcribe(b"image")


def test_vision_ocr_sends_image_to_configured_provider():
    completions = FakeCompletions(content=r"$\frac{d}{dx}x^2 = 2x$")
    client = OCRClient(
        api_key="test-key",
        base_url="https://vision.example/v1",
        model="vision-test",
        provider="test-provider",
        client=FakeVisionClient(completions),
    )

    transcript = client.transcribe(b"png-bytes", "image/png")

    assert transcript == r"$\frac{d}{dx}x^2 = 2x$"
    assert completions.last_request["model"] == "vision-test"
    content = completions.last_request["messages"][0]["content"]
    assert content[0]["type"] == "image_url"
    assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert content[1]["type"] == "text"


def test_vision_ocr_converts_provider_errors_to_safe_domain_error():
    completions = FakeCompletions(error=RuntimeError("provider secret details"))
    client = OCRClient(
        api_key="test-key",
        base_url="https://vision.example/v1",
        model="vision-test",
        client=FakeVisionClient(completions),
    )

    with pytest.raises(OCRTranscriptionError, match="could not read"):
        client.transcribe(b"image")
