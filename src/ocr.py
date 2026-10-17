"""Dedicated vision OCR layer for handwriting-to-LaTeX transcription.

DeepSeek remains the text reasoning and grading model. This module deliberately
uses a separate, explicitly configured vision-capable provider and never falls
back to sending images to a text-only model.
"""
import base64
import logging
from typing import Any

from openai import OpenAI

from src.config import Config

logger = logging.getLogger(__name__)

OCR_PROMPT = """You are a precise mathematical handwriting OCR engine.

A student has handwritten their mathematical solution naturally (not LaTeX).
They wrote math symbols, formulas, equations, and derivations by hand.

Your task: Transcribe ALL visible handwritten content faithfully:
- Output ONLY the transcribed content — no greetings, no commentary.
- The student wrote NATURAL math (fractions, integrals, sums, matrices, etc.).
  Convert it to LaTeX notation: $...$ for inline math, $$...$$ for display math.
- Preserve every step the student wrote, in the original order.
- If a symbol or number is unclear, mark it as [?].
- If you see a diagram or graph, describe it briefly in [brackets].
- Do NOT solve, correct, or complete the student's work. Transcribe faithfully.
- Remember: the student wrote HANDWRITTEN MATH, not LaTeX code."""


class OCRConfigurationError(RuntimeError):
    """Raised when no dedicated vision OCR provider is configured."""


class OCRTranscriptionError(RuntimeError):
    """Raised when the vision provider cannot produce a usable transcript."""


class OCRClient:
    """Handwriting transcription client backed by a dedicated vision model."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        client: Any | None = None,
    ):
        self.api_key = Config.VISION_API_KEY if api_key is None else api_key
        self.base_url = Config.VISION_BASE_URL if base_url is None else base_url
        self.model = Config.VISION_MODEL if model is None else model
        self.provider = Config.VISION_PROVIDER if provider is None else provider
        self.client = client

        if self.client is None and self.configured:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            logger.info(
                "Vision OCR client initialized (Provider: %s, Model: %s)",
                self.provider,
                self.model,
            )
        elif not self.configured:
            logger.warning(
                "Vision OCR is not configured. Set VISION_API_KEY, "
                "VISION_BASE_URL, and VISION_MODEL to enable photo review."
            )

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    def status(self) -> dict[str, str | bool]:
        return {
            "configured": self.configured,
            "provider": self.provider,
            "model": self.model if self.configured else "",
        }

    def transcribe(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
        """
        Transcribe handwritten math from an image into LaTeX text.

        Returns the transcribed text. Configuration and provider failures are
        explicit so the API can return a safe, actionable error to the client.
        """
        if not self.configured or self.client is None:
            raise OCRConfigurationError(
                "Photo review is unavailable because a dedicated vision OCR "
                "provider has not been configured."
            )
        if not image_bytes:
            raise OCRTranscriptionError("The uploaded image is empty.")

        b64 = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:{mime_type};base64,{b64}"

        try:
            logger.info(
                "Vision OCR transcription started (Provider: %s, Model: %s)",
                self.provider,
                self.model,
            )
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": data_url}},
                            {"type": "text", "text": OCR_PROMPT},
                        ],
                    }
                ],
                temperature=0.1,
                max_tokens=Config.VISION_MAX_TOKENS,
            )
            text = response.choices[0].message.content if response.choices else ""
            transcript = (text or "").strip()
            if not transcript:
                raise OCRTranscriptionError(
                    "The vision OCR provider returned an empty transcript."
                )
            logger.info("Vision OCR complete (%s characters)", len(transcript))
            return transcript
        except OCRTranscriptionError:
            raise
        except Exception as error:
            logger.error("Vision OCR request failed: %s", error)
            raise OCRTranscriptionError(
                "The vision OCR provider could not read the uploaded work."
            ) from error
