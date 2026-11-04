"""Optional Gemini Vision enrichment for document images."""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
from pathlib import Path
from typing import Any, Literal

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from . import config

logger = logging.getLogger(__name__)


class VisualAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visual_type: Literal[
        "photo", "diagram", "flowchart", "chart", "table", "ui_screenshot", "other"
    ] = Field(description="Jenis visual")
    title: str = ""
    description: str
    visible_text: list[str] = Field(default_factory=list)
    key_facts: list[str] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)

    @field_validator("description")
    @classmethod
    def require_description(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Visual description must not be empty")
        return value

    @field_validator("visible_text", "key_facts", "relationships")
    @classmethod
    def require_nonempty_items(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("Visual analysis lists must not contain empty items")
        return [value.strip() for value in values]


VISION_PROMPT = """
Analisis gambar ini sebagai sumber pengetahuan untuk sistem RAG dokumen.
Gunakan hanya informasi yang benar-benar terlihat. Jangan menambah pengetahuan
umum atau membuat asumsi.

Hasil OCR:
{ocr_text}

Konteks teks di sekitar gambar:
{surrounding_text}

Isi keluaran terstruktur sesuai skema berikut:
{{
  "visual_type": "photo|diagram|flowchart|chart|table|ui_screenshot|other",
  "title": "judul yang terlihat atau string kosong",
  "description": "deskripsi ringkas dalam Bahasa Indonesia",
  "visible_text": ["teks penting yang terlihat"],
  "key_facts": ["fakta yang dapat dibuktikan dari gambar"],
  "relationships": ["hubungan, urutan, atau tren yang terlihat"]
}}
""".strip()


def _response_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content)


def _parse_visual_analysis(raw_text: str) -> VisualAnalysis:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```")
        text = text.removesuffix("```").strip()
    try:
        return VisualAnalysis.model_validate_json(text)
    except (ValidationError, json.JSONDecodeError):
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            raise
        return VisualAnalysis.model_validate_json(text[start:end + 1])


def analyze_image(
    file_path: Path,
    ocr_text: str = "",
    surrounding_text: str = "",
) -> VisualAnalysis | None:
    """Analyze an image only when external Vision processing is enabled."""
    if not config.VISION_ENABLED or not config.GEMINI_API_KEY:
        return None

    mime_type = mimetypes.guess_type(file_path.name)[0] or "image/png"
    encoded_image = base64.b64encode(file_path.read_bytes()).decode("ascii")
    prompt = VISION_PROMPT.format(
        ocr_text=ocr_text[:config.VISION_CONTEXT_MAX_CHARS] or "(tidak ada)",
        surrounding_text=(
            surrounding_text[:config.VISION_CONTEXT_MAX_CHARS] or "(tidak ada)"
        ),
    )
    message = HumanMessage(content=[
        {"type": "text", "text": prompt},
        {
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{encoded_image}"},
        },
    ])

    try:
        model = ChatGoogleGenerativeAI(
            model=config.GEMINI_VISION_MODEL,
            google_api_key=config.GEMINI_API_KEY,
            temperature=0,
            max_output_tokens=config.GEMINI_VISION_MAX_TOKENS,
            streaming=False,
        )
        response = model.with_structured_output(
            VisualAnalysis, method="json_schema"
        ).invoke([message])
        return VisualAnalysis.model_validate(response)
    except Exception:  # noqa: BLE001 - Vision is optional enrichment
        logger.exception("Gemini Vision analysis failed for %s", file_path.name)
        return None


def format_visual_analysis(analysis: VisualAnalysis | None) -> str:
    if analysis is None:
        return ""
    lines = ["[Analisis visual]", f"Jenis visual: {analysis.visual_type}"]
    if analysis.title:
        lines.append(f"Judul: {analysis.title}")
    lines.append(f"Deskripsi: {analysis.description}")
    if analysis.visible_text:
        lines.append("Teks terlihat: " + "; ".join(analysis.visible_text))
    if analysis.key_facts:
        lines.append("Fakta visual: " + "; ".join(analysis.key_facts))
    if analysis.relationships:
        lines.append("Hubungan visual: " + "; ".join(analysis.relationships))
    return "\n".join(lines)
