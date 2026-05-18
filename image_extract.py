"""
Image → searchable plain text with two explicitly separated pipelines:

- **VISUAL DESCRIPTION**: Gemini Vision only (scene, objects, layout). Never Tesseract.
- **OCR TEXT**: Tesseract only (`lang=heb+eng`). Visible glyphs only — not a substitute
  for visual understanding.

``app.py`` prefixes ``# kb_image_visual`` / ``# kb_gemini_visual`` for runtime checks.
Stored body::

    VISUAL DESCRIPTION:
    ...

    OCR TEXT:
    ...

Older indexed files may still use legacy ``Image visual description`` /
``OCR text`` headings; ``rag_engine`` accepts both formats.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

from google.genai import types
from PIL import Image


# Gemini: visual narration only — Tesseract fills OCR independently.
GEMINI_SCENE_ONLY_PROMPT = """You are creating a searchable **visual scene description**
for one image.

Describe what is visible: principal objects or people, background, spatial layout,
notable colours or materials, prominent UI layout (if screenshot), mood/lighting when
meaningful.

**Do not** transcribe readable text verbatim (menus, captions, handwriting, signage).
Assume a separate OCR pass will capture visible text exactly.

Respond with plain prose — **three to eight sentences**. No headings, no bullets."""


FRIENDLY_NO_VISION_NO_OCR_EN = (
    "Gemini Vision did not run (quota exhausted, network issue, missing key, or "
    "service error). OCR only reads visible text, and none was detected in "
    "this image — try later, check your API key, or use a sharper photo."
)
FRIENDLY_NO_VISION_NO_OCR_HE = (
    "Gemini Vision לא זמין (מכסה, בעיית רשת, מפתח חסר או שירות). "
    "OCR קורא רק טקסט גלוי ולא זוהה כזה בתמונה — נסה שוב מאוחר יותר, "
    "ודא שהמפתח מוגדר, או העלה תמונה חדה יותר."
)

NO_TEXT_AFTER_EMPTY_GEMINI_MSG = (
    "Gemini Vision did not produce a visual description for this upload, and OCR "
    "found no readable text either."
)


def compose_kb_visual_ocr_sections(
    visual: str | None,
    ocr_body: str,
    *,
    visual_is_placeholder: bool,
) -> str:
    """Build stored ``VISUAL DESCRIPTION`` / ``OCR TEXT`` block."""
    v_plain = (
        ""
        if visual_is_placeholder or not ((visual or "").strip())
        else (visual or "").strip()
    )
    if visual_is_placeholder or not v_plain.strip():
        v_vis = (
            "(Unavailable — Gemini Vision did not provide a visual description. OCR "
            "cannot infer objects or scenes.)"
        )
    else:
        v_vis = v_plain
    o = (ocr_body or "").strip()
    if not o:
        o = "No readable text found."
    return (
        "VISUAL DESCRIPTION:\n"
        f"{v_vis}\n\n"
        "OCR TEXT:\n"
        f"{o}\n"
    )


def is_quota_exhausted(exc: BaseException) -> bool:
    lowered = str(exc).lower()
    if "429" in lowered:
        return True
    if "resource_exhausted" in lowered or "resource exhausted" in lowered:
        return True
    if "quota" in lowered and (
        "exceed" in lowered or "limit" in lowered or "ran out" in lowered
    ):
        return True

    status = getattr(exc, "status_code", None)
    if status == 429:
        return True

    alt_code = getattr(exc, "code", None)
    if isinstance(alt_code, int) and alt_code == 429:
        return True
    alt_s = getattr(alt_code, "value", alt_code)
    if isinstance(alt_s, str) and "resource_exhausted" in alt_s.lower():
        return True

    return False


class GeminiVisionError(Exception):
    """Non-recoverable (non-quota) Gemini Vision failure."""

    def __init__(self, public_message: str) -> None:
        super().__init__(public_message)
        self.public_message = public_message


@dataclass(frozen=True)
class ImageExtractResult:
    """Outcome of ingestion just before persistence under ``generated/*.extracted.txt``."""

    text: str | None
    method: str | None
    failure_message: str | None
    has_visual_understanding: bool
    upload_notice: str | None


def _clean_ocr(raw: str) -> str:
    text = raw.replace("\x00", "") if raw else ""
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_scene_with_gemini(
    client,
    model: str,
    image_bytes: bytes,
    mime_type: str,
) -> str:
    response = client.models.generate_content(
        model=model,
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=GEMINI_SCENE_ONLY_PROMPT),
                    types.Part(
                        inline_data=types.Blob(
                            data=image_bytes,
                            mime_type=mime_type,
                        )
                    ),
                ],
            )
        ],
        config=types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=4096,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return (response.text or "").strip()


def extract_with_tesseract(image_bytes: bytes) -> str:
    import pytesseract

    try:
        img = Image.open(io.BytesIO(image_bytes))
    except OSError:
        return ""

    if img.mode not in ("RGB", "L"):
        try:
            img = img.convert("RGB")
        except OSError:
            return ""

    try:
        raw = pytesseract.image_to_string(img, lang="heb+eng")
    except pytesseract.TesseractNotFoundError:
        return ""
    except Exception:
        return ""

    return _clean_ocr(raw)


def extract_image_text_for_rag(
    client,
    model: str | None,
    image_bytes: bytes,
    mime_type: str,
) -> ImageExtractResult:
    ocr_tesseract = extract_with_tesseract(image_bytes)
    bilingual_fail_txt = (
        f"{FRIENDLY_NO_VISION_NO_OCR_EN}\n{FRIENDLY_NO_VISION_NO_OCR_HE}"
    )

    quota_hit = False
    gemini_attempted = False

    gemini_visual: str = ""

    if client and model:
        gemini_attempted = True
        try:
            gemini_visual = extract_scene_with_gemini(
                client, model, image_bytes, mime_type
            ).strip()
        except Exception as exc:  # noqa: BLE001
            if is_quota_exhausted(exc):
                quota_hit = True
            else:
                raise GeminiVisionError(
                    "Gemini Vision returned an error while analyzing this image "
                    "(this is separate from quota: the service failed or timed out). "
                    "Retry in a few minutes, or use an image where on-screen text is "
                    "large and sharp so OCR can index it anyway."
                ) from exc

    visual_ok = bool(gemini_visual.strip()) and len(gemini_visual.strip()) >= 12

    if visual_ok:
        kb = compose_kb_visual_ocr_sections(
            gemini_visual, ocr_tesseract, visual_is_placeholder=False
        )
        return ImageExtractResult(
            text=kb,
            method="gemini_visual_plus_tesseract",
            failure_message=None,
            has_visual_understanding=True,
            upload_notice=None,
        )

    if gemini_attempted and not quota_hit:
        if ocr_tesseract:
            kb = compose_kb_visual_ocr_sections(
                None, ocr_tesseract, visual_is_placeholder=True
            )
            return ImageExtractResult(
                text=kb,
                method="gemini_empty_tesseract_ocr",
                failure_message=None,
                has_visual_understanding=False,
                upload_notice=None,
            )

        return ImageExtractResult(
            text=None,
            method=None,
            failure_message=bilingual_fail_txt + "\n" + NO_TEXT_AFTER_EMPTY_GEMINI_MSG,
            has_visual_understanding=False,
            upload_notice=None,
        )

    if gemini_attempted and quota_hit:
        if ocr_tesseract:
            kb = compose_kb_visual_ocr_sections(
                None, ocr_tesseract, visual_is_placeholder=True
            )
            return ImageExtractResult(
                text=kb,
                method="quota_tesseract_ocr",
                failure_message=None,
                has_visual_understanding=False,
                upload_notice=None,
            )

        return ImageExtractResult(
            text=None,
            method=None,
            failure_message=bilingual_fail_txt,
            has_visual_understanding=False,
            upload_notice=None,
        )

    if ocr_tesseract:
        kb = compose_kb_visual_ocr_sections(
            None, ocr_tesseract, visual_is_placeholder=True
        )
        return ImageExtractResult(
            text=kb,
            method="local_tesseract_only",
            failure_message=None,
            has_visual_understanding=False,
            upload_notice=None,
        )

    return ImageExtractResult(
        text=None,
        method=None,
        failure_message=bilingual_fail_txt,
        has_visual_understanding=False,
        upload_notice=None,
    )
