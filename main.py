"""Desktop PDF to audiobook converter.

This module provides a Tkinter application that extracts text from a PDF with
pypdf and converts it to an MP3 audiobook using edge-tts.
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import traceback
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

import edge_tts
from PIL import Image, ImageTk
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from lesson_builder import LessonBuilder, analyze_lesson_structure

APP_TITLE = "EchoLearn"
LOGO_FILE = "echolearn_logo.png"
CUSTOM_CURSOR_ENABLED = False
DEFAULT_RATE = 0
DEFAULT_VOLUME = 0
DEFAULT_ENGLISH_VOICE = "en-US-JennyNeural"
DEFAULT_SPANISH_VOICE = "es-CO-SalomeNeural"
DEFAULT_UNTAGGED_LANGUAGE = "EN"
DEFAULT_AUTO_DETECT_LANGUAGE = True
DEFAULT_AUTO_LEARNING_PAUSES_ENABLED = False
DEFAULT_AUTO_PAUSE_SECONDS = 3
DEFAULT_AUTO_PAUSE_SEGMENTATION = "paragraph"
DEFAULT_CONVERSION_MODE = "audiobook"
DEFAULT_THEME_PREFERENCE = "System"
DEFAULT_REMEMBER_LAST_SELECTED_MODE = True
DEFAULT_ECHOLESSON_GENERATION_MODE = "Standard"
CONVERSION_MODE_OPTIONS = {
    "Audiobook": "audiobook",
    "EchoLesson": "echolesson",
}
THEME_OPTIONS = ("System", "Dark", "Light")
ECHOLESSON_GENERATION_MODE_OPTIONS = ("Standard", "AI Enhanced")
AUDIOBOOK_MODE_DESCRIPTION = (
    "Convert your PDF into natural audio that is easy to listen to."
)
ECHOLESSON_MODE_DESCRIPTION = (
    "Transform educational content into guided learning audio."
)
RATE_OPTIONS = {
    "Very Slow": -50,
    "Slow": -25,
    "Normal": 0,
    "Fast": 25,
    "Very Fast": 50,
}
VOLUME_OPTIONS = {
    "Very Low": -50,
    "Low": -25,
    "Normal": 0,
    "High": 25,
    "Very High": 50,
}
AUTO_PAUSE_OPTIONS = {
    "1 second": 1,
    "2 seconds": 2,
    "3 seconds": 3,
    "5 seconds": 5,
    "8 seconds": 8,
}
AUTO_PAUSE_SEGMENTATION_OPTIONS = {
    "Paragraph": "paragraph",
    "Sentence": "sentence",
}
SUPPORTED_PAUSES = {1, 2, 3, 5, 10}
ECHOLESSON_SUPPORTED_PAUSES = {1, 2, 3, 5, 8, 10}
TAG_PATTERN = re.compile(r"\[(EN|ES|PAUSE_(\d+)|PAUSE_[^\]]+)\]", re.IGNORECASE)
TAG_ONLY_PATTERN = re.compile(r"^\[(EN|ES|PAUSE_\d+)\]$", re.IGNORECASE)
ECHOLESSON_TAG_PATTERN = re.compile(
    r"^\[(TITLE|FLOW|EXPLANATION|DIALOG|PRACTICE|REVIEW|SPEAKER_1|SPEAKER_2|EN|ES|PAUSE_(\d+)|PAUSE_[^\]]+)\]$",
    re.IGNORECASE,
)
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
SENTENCE_ENDING_PUNCTUATION = ".!?:;"
SPANISH_CHARACTER_PATTERN = re.compile(r"[áéíóúüñÁÉÍÓÚÜÑ¿¡]")
WORD_PATTERN = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ']+")
SPANISH_WORDS = {
    "al",
    "algo",
    "abandonan",
    "ahora",
    "atencion",
    "atención",
    "bien",
    "como",
    "con",
    "conversacion",
    "conversación",
    "cuando",
    "de",
    "del",
    "desde",
    "donde",
    "el",
    "ella",
    "ellos",
    "en",
    "era",
    "es",
    "esta",
    "estas",
    "este",
    "estos",
    "estoy",
    "excelente",
    "expresion",
    "expresión",
    "fue",
    "gracias",
    "hay",
    "hola",
    "idioma",
    "ingles",
    "inglés",
    "instruccion",
    "instrucción",
    "intenta",
    "la",
    "las",
    "leccion",
    "lección",
    "lo",
    "los",
    "mas",
    "mi",
    "mis",
    "muchas",
    "muy",
    "nivel",
    "nos",
    "objetivo",
    "para",
    "personas",
    "pero",
    "por",
    "porque",
    "practica",
    "práctica",
    "pronto",
    "propio",
    "que",
    "repite",
    "escucha",
    "significa",
    "sin",
    "responder",
    "su",
    "sus",
    "tambien",
    "también",
    "te",
    "tiene",
    "todavia",
    "todavía",
    "tu",
    "un",
    "una",
    "uno",
    "voz",
    "y",
    "yo",
}
STRONG_SPANISH_WORDS = {
    "atencion",
    "atención",
    "bien",
    "conversacion",
    "conversación",
    "escucha",
    "excelente",
    "expresion",
    "expresión",
    "gracias",
    "hola",
    "ingles",
    "inglés",
    "instruccion",
    "instrucción",
    "intenta",
    "leccion",
    "lección",
    "nivel",
    "practica",
    "práctica",
    "repite",
    "responder",
    "significa",
    "todavia",
    "todavía",
}
STANDALONE_INSTRUCTION_LINES = {
    "ahora escucha",
    "escucha y repite",
    "excelente",
    "muy bien",
    "repite",
}
HEADING_KEYWORDS = {
    "capitulo",
    "echolearn",
    "leccion",
    "nivel",
    "unidad",
}
WRAP_CONTINUATION_WORDS = {
    "a",
    "al",
    "and",
    "between",
    "con",
    "de",
    "del",
    "en",
    "for",
    "in",
    "of",
    "para",
    "que",
    "the",
    "to",
    "with",
    "y",
}
PRACTICE_MODE_TRIGGER_PHRASES = {
    "answer before you hear",
    "ahora escucha y repite",
    "como dirias",
    "despues de cada instruccion",
    "escucha y repite",
    "intenta responder",
    "listen and repeat",
    "practice",
    "practica",
    "repeat",
    "repite",
    "repite en voz alta",
    "say it out loud",
    "try to answer",
}
PRACTICE_MODE_EXIT_PHRASES = {
    "ahora escucha la conversacion completa",
    "ahora vamos a aprender",
    "eso es todo por hoy",
    "excellent",
    "excelente",
    "hasta la proxima leccion",
    "muy bien",
    "now listen to the full conversation",
    "that is all for today",
    "very good",
}
ENGLISH_WORDS = {
    "a",
    "about",
    "and",
    "answer",
    "are",
    "as",
    "at",
    "be",
    "because",
    "but",
    "can",
    "do",
    "english",
    "excuse",
    "for",
    "from",
    "have",
    "he",
    "her",
    "his",
    "i",
    "if",
    "in",
    "is",
    "it",
    "listen",
    "me",
    "my",
    "not",
    "of",
    "on",
    "or",
    "our",
    "practice",
    "repeat",
    "say",
    "she",
    "so",
    "speak",
    "that",
    "the",
    "their",
    "there",
    "they",
    "this",
    "today",
    "to",
    "try",
    "going",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "will",
    "with",
    "you",
    "your",
}
UNCERTAIN_DETECTION_WARNING = (
    "Some text was processed using the default language because EchoLearn could "
    "not detect the language confidently."
)
DEBUG_MODE = True
APP_DATA_DIR = Path.home() / "Library" / "Application Support" / APP_TITLE
LOGS_DIR = APP_DATA_DIR / "logs"
DEBUG_SEGMENTS_FILE = LOGS_DIR / "debug_segments.txt"
DEBUG_NORMALIZED_TEXT_FILE = LOGS_DIR / "debug_normalized_text.txt"
LANGUAGE_DETECTION_DEBUG_FILE = LOGS_DIR / "language_detection_debug.txt"
SMART_CLEANUP_DEBUG_FILE = LOGS_DIR / "smart_cleanup_debug.txt"
SETTINGS_FILE = APP_DATA_DIR / "config.json"
LEGACY_SETTINGS_FILE = APP_DATA_DIR / "echolearn_settings.json"
FFMPEG_NOT_FOUND_MESSAGE = (
    "FFmpeg was not found.\n"
    "Expected locations:\n"
    "- /opt/homebrew/bin/ffmpeg\n"
    "- /usr/local/bin/ffmpeg\n\n"
    "Install with:\n\n"
    "brew install ffmpeg"
)


def asset_path(filename: str) -> Path:
    """Return an asset path for source and PyInstaller builds."""

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets" / filename  # type: ignore[attr-defined]

    return Path(__file__).resolve().parent / "assets" / filename


def ensure_app_directories() -> None:
    """Create writable user data folders used by packaged macOS builds."""

    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def log_runtime_paths(output_path: Path | None = None) -> None:
    """Print the app's writable paths for terminal/debug builds."""

    print(f"App data directory: {APP_DATA_DIR}")
    print(f"Temp directory: {tempfile.gettempdir()}")
    if output_path is not None:
        print(f"Output path: {output_path}")


def get_ffmpeg_path() -> str:
    """Find FFmpeg in Terminal PATH or common macOS Homebrew locations."""

    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        print(f"FFmpeg detected at:\n{ffmpeg_path}")
        return ffmpeg_path

    for candidate in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            print(f"FFmpeg detected at:\n{candidate}")
            return candidate

    raise PDFAudiobookError(FFMPEG_NOT_FOUND_MESSAGE)


class PDFAudiobookError(Exception):
    """Base exception for user-facing PDF audiobook errors."""


class EmptyPDFError(PDFAudiobookError):
    """Raised when a PDF contains no pages."""


class NoExtractableTextError(PDFAudiobookError):
    """Raised when no selectable text can be extracted from the PDF."""


@dataclass(frozen=True)
class VoiceOption:
    """A voice option exposed to the user."""

    label: str
    voice_id: str
    gender: str


@dataclass(frozen=True)
class ConversionSettings:
    """Settings selected by the user before conversion starts."""

    conversion_mode: str
    lesson_markup: str
    speaker_1_voice_id: str
    speaker_2_voice_id: str
    pdf_path: Path
    output_path: Path
    english_voice_id: str
    spanish_voice_id: str
    rate: int
    volume: int
    auto_detect_language: bool
    default_untagged_language: str
    auto_learning_pauses: bool
    auto_pause_seconds: int
    auto_pause_segmentation: str


@dataclass(frozen=True)
class VoicePreviewSettings:
    """Voice settings selected by the user for a short preview."""

    english_voice_id: str
    spanish_voice_id: str
    rate: int
    volume: int


@dataclass(frozen=True)
class ScriptSegment:
    """A text or pause segment that will become part of the final MP3."""

    kind: str
    text: str = ""
    voice_id: str = ""
    language: str = "EN"
    seconds: int = 0
    section_type: str = "FLOW"
    pause_after: int = 0
    language_source: str = "default"
    detection_confident: bool = True
    detection_score: int = 0
    auto_pause_after: bool = True
    raw_text_unit: str = ""
    practice_mode: bool = False
    practice_trigger: str = ""
    practice_pause_inserted: bool = False


@dataclass(frozen=True)
class SmartCleanupRecord:
    """Mapping from extracted PDF lines to the cleaned segment EchoLearn uses."""

    raw_line: str
    cleaned_segment: str


@dataclass(frozen=True)
class ConversionResult:
    """Result details shown to the user when conversion completes."""

    output_path: Path
    warnings: list[str]


@dataclass(frozen=True)
class ProgressMessage:
    """Message sent from the worker thread to the Tkinter UI thread."""

    kind: str
    payload: Any = None


def normalize_text(text: str) -> str:
    """Clean extracted PDF text so speech sounds more natural."""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(
        r"\[\s*(EN|ES|PAUSE_\d+)\s*\n\s*\]",
        lambda match: f"[{match.group(1).upper()}]",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalized_line_key(line: str) -> str:
    """Return a normalized key for exact short-line cleanup rules."""

    return normalize_text(line).lower().rstrip(".!?:;")


def normalized_phrase_text(text: str) -> str:
    """Return accent-insensitive text for phrase matching."""

    decomposed = unicodedata.normalize("NFKD", normalize_text(text).lower())
    without_accents = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9']+", " ", without_accents).strip()


def matching_phrase(text: str, phrases: set[str]) -> str:
    """Return the first configured phrase found in text."""

    normalized_text = f" {normalized_phrase_text(text)} "
    for phrase in sorted(phrases, key=len, reverse=True):
        normalized_phrase = normalized_phrase_text(phrase)
        if f" {normalized_phrase} " in normalized_text:
            return phrase
    return ""


def is_standalone_instruction_line(line: str) -> bool:
    """Return True for short instruction prompts that should not be merged."""

    return normalized_line_key(line) in STANDALONE_INSTRUCTION_LINES


def extract_text_from_pdf(
    pdf_path: Path,
    progress_callback: Callable[[int, int], None],
) -> str:
    """Extract text from every page of a PDF and report page progress."""

    try:
        reader = PdfReader(str(pdf_path))
    except (PdfReadError, OSError, ValueError) as exc:
        raise PDFAudiobookError(
            "The selected file could not be opened as a valid PDF."
        ) from exc

    total_pages = len(reader.pages)
    if total_pages == 0:
        raise EmptyPDFError("The selected PDF does not contain any pages.")

    page_texts: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            traceback.print_exc()
            raise

        cleaned_text = normalize_text(text)
        if cleaned_text:
            page_texts.append(cleaned_text)

        progress_callback(index, total_pages)

    full_text = normalize_text("\n\n".join(page_texts))
    if not full_text:
        raise NoExtractableTextError(
            "No extractable text was found. This may be a scanned PDF or an "
            "image-only document."
        )

    return full_text


def has_sentence_ending(text: str) -> bool:
    """Return True when text ends with sentence boundary punctuation."""

    return text.rstrip().endswith(tuple(SENTENCE_ENDING_PUNCTUATION))


def first_text_character(text: str) -> str:
    """Return the first non-space character, if present."""

    stripped_text = text.strip()
    return stripped_text[0] if stripped_text else ""


def looks_like_heading(line: str, next_line: str | None = None) -> bool:
    """Return True for short standalone title-like lines."""

    normalized_line = normalize_text(line)
    if (
        not normalized_line
        or has_sentence_ending(normalized_line)
        or is_standalone_instruction_line(normalized_line)
    ):
        return False

    words = WORD_PATTERN.findall(normalized_line)
    if not words or len(words) > 12:
        return False

    lower_words = {word.lower() for word in words}
    has_heading_keyword = bool(lower_words & HEADING_KEYWORDS)
    if has_heading_keyword and ("-" in normalized_line or len(words) <= 6):
        return True

    title_case_words = [word for word in words if word[0].isupper()]
    next_character = first_text_character(next_line or "")
    return len(title_case_words) == len(words) or (
        has_heading_keyword and next_character.isupper()
    )


def looks_like_short_english_dialogue_line(line: str) -> bool:
    """Return True for compact English dialogue lines that should stand alone."""

    cleaned_line = normalize_text(line)
    if not cleaned_line or not cleaned_line.endswith((".", "?", "!")):
        return False

    words = [word.lower() for word in WORD_PATTERN.findall(cleaned_line)]
    if not words or len(words) > 8:
        return False

    english_score = sum(1 for word in words if word in ENGLISH_WORDS)
    spanish_score = sum(1 for word in words if word in SPANISH_WORDS)
    if spanish_score > english_score or english_score == 0:
        return False

    conversational_starters = {
        "are",
        "can",
        "could",
        "do",
        "does",
        "excuse",
        "hello",
        "hey",
        "hi",
        "how",
        "i",
        "is",
        "may",
        "please",
        "thank",
        "thanks",
        "what",
        "where",
        "would",
        "you",
    }
    return cleaned_line.endswith("?") or words[0] in conversational_starters


def should_merge_wrapped_lines(
    current_line: str,
    next_line: str,
    following_line: str | None = None,
) -> bool:
    """Return True when adjacent extracted PDF lines are one wrapped sentence."""

    current_line = normalize_text(current_line)
    next_line = normalize_text(next_line)
    if (
        not current_line
        or not next_line
        or has_sentence_ending(current_line)
        or TAG_ONLY_PATTERN.fullmatch(current_line)
        or TAG_ONLY_PATTERN.fullmatch(next_line)
        or is_standalone_instruction_line(current_line)
        or is_standalone_instruction_line(next_line)
        or looks_like_heading(current_line, next_line)
        or looks_like_heading(next_line, following_line)
    ):
        return False

    next_character = first_text_character(next_line)
    if next_character and next_character.islower():
        return True

    current_words = [word.lower() for word in WORD_PATTERN.findall(current_line)]
    next_words = WORD_PATTERN.findall(next_line)
    if current_words and current_words[-1] in WRAP_CONTINUATION_WORDS:
        return True

    if len(current_line) >= 55 and next_words and len(next_words) <= 4:
        return True

    return len(current_line) >= 55 and bool(next_character) and not next_character.isupper()


def add_missing_sentence_punctuation(text: str, *, standalone: bool) -> str:
    """Add a period to sentence-like cleanup units without changing headings."""

    cleaned_text = normalize_text(text)
    if standalone or not cleaned_text or has_sentence_ending(cleaned_text):
        return cleaned_text
    if TAG_ONLY_PATTERN.fullmatch(cleaned_text):
        return cleaned_text
    return f"{cleaned_text}."


def smart_pdf_cleanup_span(
    span_text: str,
) -> tuple[list[list[str]], list[SmartCleanupRecord]]:
    """Repair wrapped PDF lines inside text that does not contain manual tags."""

    cleaned_paragraphs: list[list[str]] = []
    records: list[SmartCleanupRecord] = []
    normalized_span = normalize_text(span_text)
    paragraphs = [
        paragraph
        for paragraph in re.split(r"\n\s*\n", normalized_span)
        if normalize_text(paragraph)
    ]

    for paragraph in paragraphs:
        cleaned_segments: list[str] = []
        lines = [
            normalized_line
            for line in paragraph.splitlines()
            if (normalized_line := normalize_text(line))
        ]
        index = 0
        while index < len(lines):
            line = lines[index]
            next_line = lines[index + 1] if index + 1 < len(lines) else None
            if is_standalone_instruction_line(line):
                segment = add_missing_sentence_punctuation(line, standalone=True)
                cleaned_segments.append(segment)
                records.append(SmartCleanupRecord(raw_line=line, cleaned_segment=segment))
                index += 1
                continue
            if looks_like_heading(line, next_line):
                cleaned_segments.append(line)
                records.append(SmartCleanupRecord(raw_line=line, cleaned_segment=line))
                index += 1
                continue

            raw_lines = [line]
            merged_line = line
            index += 1
            while index < len(lines):
                candidate_line = lines[index]
                following_line = lines[index + 1] if index + 1 < len(lines) else None
                if not should_merge_wrapped_lines(
                    merged_line,
                    candidate_line,
                    following_line,
                ):
                    break
                raw_lines.append(candidate_line)
                merged_line = normalize_text(f"{merged_line} {candidate_line}")
                index += 1

            segment = add_missing_sentence_punctuation(merged_line, standalone=False)
            cleaned_segments.append(segment)
            records.append(
                SmartCleanupRecord(
                    raw_line="\n".join(raw_lines),
                    cleaned_segment=segment,
                )
            )

        if cleaned_segments:
            cleaned_paragraphs.append(cleaned_segments)

    return cleaned_paragraphs, records


def smart_pdf_cleanup(text: str) -> tuple[str, list[SmartCleanupRecord]]:
    """Clean extracted PDF lines before language detection and audio parsing."""

    cleaned_parts: list[str] = []
    cleanup_records: list[SmartCleanupRecord] = []
    position = 0
    for match in TAG_PATTERN.finditer(text):
        span_paragraphs, span_records = smart_pdf_cleanup_span(text[position : match.start()])
        cleaned_parts.extend(
            "\n".join(paragraph_segments)
            for paragraph_segments in span_paragraphs
        )
        cleanup_records.extend(span_records)
        cleaned_parts.append(f"[{match.group(1).upper()}]")
        position = match.end()

    span_paragraphs, span_records = smart_pdf_cleanup_span(text[position:])
    cleaned_parts.extend(
        "\n".join(paragraph_segments)
        for paragraph_segments in span_paragraphs
    )
    cleanup_records.extend(span_records)
    cleaned_text = normalize_text("\n\n".join(part for part in cleaned_parts if part))
    return cleaned_text, cleanup_records


def split_sentences(text: str) -> list[str]:
    """Split text into sentence-sized units while preserving order."""

    sentence_text = re.sub(r"[ \t]*\n+[ \t]*", " ", normalize_text(text))
    sentences = [
        normalize_text(sentence)
        for sentence in SENTENCE_SPLIT_PATTERN.split(sentence_text)
        if normalize_text(sentence)
    ]
    return sentences or [sentence_text]


def split_untagged_text_units(
    raw_text: str,
    *,
    auto_pause_segmentation: str = DEFAULT_AUTO_PAUSE_SEGMENTATION,
) -> list[tuple[str, str]]:
    """Build final heading, sentence, or idea-block units before detection."""

    cleaned_text = normalize_text(raw_text)
    if not cleaned_text or TAG_ONLY_PATTERN.fullmatch(cleaned_text):
        return []

    use_paragraph_blocks = auto_pause_segmentation == "paragraph"
    units: list[tuple[str, str]] = []
    paragraphs = [
        paragraph
        for paragraph in re.split(r"\n\s*\n", cleaned_text)
        if normalize_text(paragraph)
    ]
    for paragraph in paragraphs:
        lines = [
            normalized_line
            for line in paragraph.splitlines()
            if (normalized_line := normalize_text(line))
        ]
        block_lines: list[str] = []

        def flush_paragraph_block() -> None:
            if not block_lines:
                return
            block_text = normalize_text(" ".join(block_lines))
            if block_text:
                units.append((block_text, "paragraph"))
            block_lines.clear()

        index = 0
        while index < len(lines):
            line = lines[index]
            next_line = lines[index + 1] if index + 1 < len(lines) else None
            if is_standalone_instruction_line(line):
                flush_paragraph_block()
                units.append((line, "sentence"))
                index += 1
                continue
            if looks_like_heading(line, next_line):
                flush_paragraph_block()
                units.append((line, "heading"))
                index += 1
                continue

            merged_line = line
            index += 1
            while index < len(lines):
                candidate_line = lines[index]
                following_line = lines[index + 1] if index + 1 < len(lines) else None
                if not should_merge_wrapped_lines(
                    merged_line,
                    candidate_line,
                    following_line,
                ):
                    break
                merged_line = normalize_text(f"{merged_line} {candidate_line}")
                index += 1

            if use_paragraph_blocks and looks_like_short_english_dialogue_line(merged_line):
                flush_paragraph_block()
                units.append((merged_line, "sentence"))
                continue

            if use_paragraph_blocks:
                block_lines.append(merged_line)
                continue

            for sentence in split_sentences(merged_line):
                units.append((sentence, "sentence"))

        flush_paragraph_block()

    return units


def format_language_detection_debug(segment: ScriptSegment) -> str:
    """Return the exact debug block for one language detection unit."""

    auto_pause = "yes" if segment.auto_pause_after else "no"
    return (
        f"RAW TEXT UNIT:\n{segment.raw_text_unit}\n"
        f"FINAL SEGMENT:\n{segment.text}\n"
        f"LANGUAGE:\n{segment.language}\n"
        f"SOURCE:\n{segment.language_source}\n"
        f"AUTO PAUSE:\n{auto_pause}\n"
    )


def log_language_detection_unit(
    debug_entries: list[str],
    *,
    segment: ScriptSegment,
) -> None:
    """Print and collect language detection debug output."""

    debug_entry = format_language_detection_debug(segment)
    print(debug_entry, end="")
    debug_entries.append(debug_entry)


def log_sentence_detected(sentence: str) -> None:
    """Print the sentence unit used for detection and auto pauses."""

    print(f"SENTENCE DETECTED:\n{sentence}")


def language_name(language: str) -> str:
    """Return the display name for an internal language code."""

    return "Spanish" if language == "ES" else "English"


def detect_language_for_text(
    text: str,
    *,
    default_language: str,
    auto_detect_language: bool,
) -> tuple[str, str, bool, int]:
    """Detect English or Spanish for untagged text using local heuristics."""

    normalized_default = "ES" if default_language == "ES" else "EN"
    if not auto_detect_language:
        return normalized_default, "default", True, 0

    normalized_text = normalize_text(text)
    words = [word.lower() for word in WORD_PATTERN.findall(normalized_text)]
    spanish_score = sum(1 for word in words if word in SPANISH_WORDS)
    english_score = sum(1 for word in words if word in ENGLISH_WORDS)
    if any(word in STRONG_SPANISH_WORDS for word in words):
        spanish_score += 2

    if SPANISH_CHARACTER_PATTERN.search(normalized_text):
        spanish_score += 3
    if "¿" in normalized_text or "¡" in normalized_text:
        spanish_score += 2

    score_delta = spanish_score - english_score
    if score_delta >= 1:
        return "ES", "auto-detect", True, score_delta
    if score_delta <= -2:
        return "EN", "auto-detect", True, abs(score_delta)
    if spanish_score > english_score and spanish_score >= 2:
        return "ES", "auto-detect", True, score_delta
    if english_score > spanish_score and english_score >= 2:
        return "EN", "auto-detect", True, abs(score_delta)

    return normalized_default, "default", False, abs(score_delta)


def language_signal_for_word(word: str) -> str | None:
    """Return a clear per-word language signal, ignoring ambiguous words."""

    normalized_word = word.lower()
    if SPANISH_CHARACTER_PATTERN.search(word):
        return "ES"

    is_spanish = normalized_word in SPANISH_WORDS
    is_english = normalized_word in ENGLISH_WORDS
    if is_spanish and not is_english:
        return "ES"
    if is_english and not is_spanish:
        return "EN"
    return None


def split_mixed_language_text(
    text: str,
    *,
    default_language: str,
    auto_detect_language: bool,
) -> list[tuple[str, str, str, bool, int]]:
    """Split one text unit on a clear mixed-language boundary."""

    base_detection = detect_language_for_text(
        text,
        default_language=default_language,
        auto_detect_language=auto_detect_language,
    )
    if not auto_detect_language:
        return [(text, *base_detection)]

    word_matches = list(WORD_PATTERN.finditer(text))
    signals = [
        (match.start(), language_signal_for_word(match.group(0)))
        for match in word_matches
    ]
    clear_signals = [
        (position, signal)
        for position, signal in signals
        if signal in {"EN", "ES"}
    ]
    if len(clear_signals) < 3:
        return [(text, *base_detection)]

    signal_languages = {signal for _position, signal in clear_signals}
    if signal_languages != {"EN", "ES"}:
        return [(text, *base_detection)]

    transitions = [
        index
        for index in range(1, len(clear_signals))
        if clear_signals[index][1] != clear_signals[index - 1][1]
    ]
    if len(transitions) != 1:
        return [(text, *base_detection)]

    transition_index = transitions[0]
    leading_signals = clear_signals[:transition_index]
    trailing_signals = clear_signals[transition_index:]
    if len(trailing_signals) < 2:
        return [(text, *base_detection)]

    boundary = clear_signals[transition_index][0]
    first_text = normalize_text(text[:boundary])
    second_text = normalize_text(text[boundary:])
    if not first_text or not second_text:
        return [(text, *base_detection)]

    first_language = leading_signals[-1][1]
    second_language = trailing_signals[0][1]
    first_score = len(leading_signals)
    second_score = len(trailing_signals)
    return [
        (first_text, first_language, "auto-detect", True, first_score),
        (second_text, second_language, "auto-detect", True, second_score),
    ]


def should_warn_about_uncertain_detection(segments: list[ScriptSegment]) -> bool:
    """Return True when many text segments needed the default language."""

    text_segments = [segment for segment in segments if segment.kind == "text"]
    uncertain_segments = [
        segment
        for segment in text_segments
        if (
            segment.language_source == "default"
            and not segment.detection_confident
        )
    ]
    if not uncertain_segments:
        return False

    uncertain_count = len(uncertain_segments)
    uncertain_ratio = uncertain_count / max(len(text_segments), 1)
    return uncertain_count >= 5 or (
        uncertain_count >= 3 and uncertain_ratio >= 0.25
    )


def should_insert_auto_pause_after_segment(
    segments: list[ScriptSegment],
    index: int,
    *,
    auto_learning_pauses_enabled: bool,
) -> bool:
    """Return True when an automatic pause should follow a parsed segment."""

    if not auto_learning_pauses_enabled:
        return False

    segment = segments[index]
    next_segment = segments[index + 1] if index + 1 < len(segments) else None
    return (
        segment.kind == "text"
        and segment.practice_pause_inserted
        and next_segment is not None
        and next_segment.kind != "pause"
    )


def annotate_practice_mode(
    segments: list[ScriptSegment],
    *,
    auto_learning_pauses_enabled: bool,
) -> list[ScriptSegment]:
    """Mark final segments as Flow or Practice and record pause decisions."""

    annotated_segments: list[ScriptSegment] = []
    practice_mode = False
    for index, segment in enumerate(segments):
        if segment.kind != "text":
            annotated_segments.append(segment)
            continue

        trigger = ""
        if segment.language_source == "heading":
            practice_mode = False
            segment_practice_mode = False
        else:
            exit_phrase = matching_phrase(segment.text, PRACTICE_MODE_EXIT_PHRASES)
            trigger_phrase = matching_phrase(segment.text, PRACTICE_MODE_TRIGGER_PHRASES)
            if exit_phrase:
                practice_mode = False
                segment_practice_mode = False
                trigger = f"exit: {exit_phrase}"
            elif trigger_phrase:
                practice_mode = True
                segment_practice_mode = True
                trigger = trigger_phrase
            else:
                segment_practice_mode = practice_mode

        next_segment = segments[index + 1] if index + 1 < len(segments) else None
        pause_inserted = (
            auto_learning_pauses_enabled
            and segment_practice_mode
            and segment.auto_pause_after
            and next_segment is not None
            and next_segment.kind != "pause"
        )
        annotated_segments.append(
            replace(
                segment,
                practice_mode=segment_practice_mode,
                practice_trigger=trigger,
                practice_pause_inserted=pause_inserted,
            )
        )

    return annotated_segments


def auto_pause_inserted_after_segments(segments: list[ScriptSegment]) -> list[int]:
    """Return 1-based final segment numbers that should receive auto pauses."""

    return [
        index + 1
        for index, _segment in enumerate(segments)
        if should_insert_auto_pause_after_segment(
            segments,
            index,
            auto_learning_pauses_enabled=True,
        )
    ]


def auto_pause_inserted_after_text_segments(segments: list[ScriptSegment]) -> list[int]:
    """Return 1-based text segment numbers that should receive auto pauses."""

    inserted_after_text_segments: list[int] = []
    text_segment_number = 0
    for index, segment in enumerate(segments):
        if segment.kind != "text":
            continue
        text_segment_number += 1
        if should_insert_auto_pause_after_segment(
            segments,
            index,
            auto_learning_pauses_enabled=True,
        ):
            inserted_after_text_segments.append(text_segment_number)
    return inserted_after_text_segments


def build_language_detection_debug_entries(
    segments: list[ScriptSegment],
    *,
    auto_learning_pauses_enabled: bool,
) -> list[str]:
    """Build debug blocks after final segment boundaries are known."""

    debug_entries: list[str] = []
    for index, segment in enumerate(segments):
        if segment.kind != "text":
            continue
        debug_segment = ScriptSegment(
            kind=segment.kind,
            text=segment.text,
            language=segment.language,
            seconds=segment.seconds,
            language_source=segment.language_source,
            detection_confident=segment.detection_confident,
            detection_score=segment.detection_score,
            auto_pause_after=should_insert_auto_pause_after_segment(
                segments,
                index,
                auto_learning_pauses_enabled=auto_learning_pauses_enabled,
            ),
            raw_text_unit=segment.raw_text_unit,
        )
        debug_entries.append(format_language_detection_debug(debug_segment))

    return debug_entries


def parse_audio_script(
    text: str,
    *,
    auto_detect_language: bool = DEFAULT_AUTO_DETECT_LANGUAGE,
    default_language: str = DEFAULT_UNTAGGED_LANGUAGE,
    language_debug_path: Path = LANGUAGE_DETECTION_DEBUG_FILE,
    auto_learning_pauses_enabled: bool = False,
    auto_pause_segmentation: str = DEFAULT_AUTO_PAUSE_SEGMENTATION,
) -> tuple[list[ScriptSegment], list[str]]:
    """Turn PDF text, tags, and auto language detection into audio requests."""

    segments: list[ScriptSegment] = []
    warnings: list[str] = []
    current_language = "EN"
    language_explicit_active = False
    position = 0

    def append_text_segment(segment: ScriptSegment) -> None:
        if segments and segments[-1].kind == "text" and segments[-1].text == segment.text:
            return
        segments.append(segment)

    def add_text_segment(raw_text: str, *, explicit_language: bool) -> None:
        cleaned_text = normalize_text(raw_text)
        if cleaned_text:
            if TAG_ONLY_PATTERN.fullmatch(cleaned_text):
                return
            if explicit_language:
                segment = ScriptSegment(
                    kind="text",
                    text=cleaned_text,
                    language=current_language,
                    language_source="explicit tag",
                    auto_pause_after=False,
                    raw_text_unit=cleaned_text,
                )
                append_text_segment(segment)
                return

            for raw_text_unit, unit_source in split_untagged_text_units(
                cleaned_text,
                auto_pause_segmentation=auto_pause_segmentation,
            ):
                log_sentence_detected(raw_text_unit)
                language, detection_source, confident, score = detect_language_for_text(
                    raw_text_unit,
                    default_language=default_language,
                    auto_detect_language=auto_detect_language,
                )
                if unit_source == "heading":
                    segment_source = "heading"
                elif unit_source == "paragraph":
                    segment_source = "paragraph"
                elif detection_source == "default":
                    segment_source = "default"
                else:
                    segment_source = "sentence"
                segment = ScriptSegment(
                    kind="text",
                    text=raw_text_unit,
                    language=language,
                    language_source=segment_source,
                    detection_confident=confident,
                    detection_score=score,
                    auto_pause_after=True,
                    raw_text_unit=raw_text_unit,
                )
                append_text_segment(segment)

    for match in TAG_PATTERN.finditer(text):
        add_text_segment(
            text[position : match.start()],
            explicit_language=language_explicit_active,
        )

        tag = match.group(1).upper()
        pause_seconds = match.group(2)

        if tag in {"EN", "ES"}:
            current_language = tag
            language_explicit_active = True
        elif pause_seconds and int(pause_seconds) in SUPPORTED_PAUSES:
            segments.append(
                ScriptSegment(kind="pause", seconds=int(pause_seconds))
            )
        else:
            warnings.append(f"Ignored unsupported pause tag [{tag}].")

        position = match.end()

    add_text_segment(text[position:], explicit_language=language_explicit_active)
    segments = annotate_practice_mode(
        segments,
        auto_learning_pauses_enabled=auto_learning_pauses_enabled,
    )
    if auto_detect_language and should_warn_about_uncertain_detection(segments):
        warnings.append(UNCERTAIN_DETECTION_WARNING)
    try:
        write_language_detection_debug(
            build_language_detection_debug_entries(
                segments,
                auto_learning_pauses_enabled=auto_learning_pauses_enabled,
            ),
            language_debug_path,
        )
    except OSError:
        traceback.print_exc()
    return segments, warnings


def parse_echolesson_markup(
    markup: str,
    *,
    speaker_1_voice_id: str,
    speaker_2_voice_id: str,
    practice_pause_seconds: int,
) -> tuple[list[ScriptSegment], list[str]]:
    """Convert EchoLearn Markup into audio segments for EchoLesson Mode."""

    segments: list[ScriptSegment] = []
    warnings: list[str] = []
    current_section = "FLOW"
    current_language = "EN"
    current_voice_id = ""

    def add_text_segment(raw_text: str) -> None:
        text = normalize_text(raw_text)
        if not text:
            return
        pause_after = (
            practice_pause_seconds
            if current_section == "PRACTICE"
            else 0
        )
        segments.append(
            ScriptSegment(
                kind="text",
                text=text,
                voice_id=current_voice_id,
                language=current_language,
                section_type=current_section,
                pause_after=pause_after,
                language_source="echolesson markup",
                auto_pause_after=False,
                raw_text_unit=text,
                practice_mode=current_section == "PRACTICE",
                practice_pause_inserted=pause_after > 0,
            )
        )
        if pause_after:
            segments.append(
                ScriptSegment(
                    kind="pause",
                    seconds=pause_after,
                    section_type=current_section,
                )
            )

    for raw_line in markup.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        tag_match = ECHOLESSON_TAG_PATTERN.match(line)
        if tag_match:
            tag = tag_match.group(1).upper()
            pause_seconds = tag_match.group(2)

            if tag in {"TITLE", "FLOW", "EXPLANATION", "DIALOG", "PRACTICE", "REVIEW"}:
                current_section = tag
                if tag != "DIALOG":
                    current_voice_id = ""
                    current_language = "EN"
                continue
            if tag == "SPEAKER_1":
                current_voice_id = speaker_1_voice_id
                current_language = "EN"
                continue
            if tag == "SPEAKER_2":
                current_voice_id = speaker_2_voice_id
                current_language = "ES"
                continue
            if tag == "EN":
                current_voice_id = ""
                current_language = "EN"
                continue
            if tag == "ES":
                current_voice_id = ""
                current_language = "ES"
                continue
            if pause_seconds:
                seconds = int(pause_seconds)
                if seconds in ECHOLESSON_SUPPORTED_PAUSES:
                    segments.append(
                        ScriptSegment(
                            kind="pause",
                            seconds=seconds,
                            section_type=current_section,
                        )
                    )
                else:
                    warnings.append(f"Ignored unsupported pause tag [{tag}].")
                continue

        if line.startswith("[") and line.endswith("]"):
            warnings.append(f"Ignored unsupported EchoLesson tag {line}.")
            continue

        add_text_segment(line)

    return segments, warnings


def log_echolesson_segments(segments: list[ScriptSegment]) -> None:
    """Print EchoLesson parser output so mode routing is easy to verify."""

    print("ECHOLESSON PARSED SEGMENTS:")
    for index, segment in enumerate(segments, start=1):
        if segment.kind == "pause":
            print(
                f"{index}. pause seconds={segment.seconds} "
                f"section={segment.section_type}"
            )
        else:
            print(
                f"{index}. text section={segment.section_type} "
                f"voice_id={segment.voice_id or 'default'} "
                f"language={segment.language} pause_after={segment.pause_after} "
                f"text={segment.text}"
            )


def add_auto_learning_pauses(
    segments: list[ScriptSegment],
    *,
    auto_pause_seconds: int,
) -> list[ScriptSegment]:
    """Insert thinking pauses after untagged learning text segments."""

    paused_segments: list[ScriptSegment] = []
    inserted_after_segments = set(auto_pause_inserted_after_segments(segments))
    for index, segment in enumerate(segments, start=1):
        paused_segments.append(segment)
        if index in inserted_after_segments:
            paused_segments.append(
                ScriptSegment(kind="pause", seconds=auto_pause_seconds)
            )
            print(
                f"Auto pause inserted: {auto_pause_seconds} seconds "
                f"after segment {index}"
            )
            print(f"AUTO PAUSE:\n{auto_pause_seconds} seconds")

    return paused_segments


def write_debug_segments(segments: list[ScriptSegment], debug_path: Path) -> None:
    """Write parsed segments to a debug file before audio generation starts."""

    debug_path.parent.mkdir(parents=True, exist_ok=True)
    with debug_path.open("w", encoding="utf-8") as debug_file:
        for index, segment in enumerate(segments, start=1):
            debug_file.write(f"Segment {index}\n")
            debug_file.write(f"kind={segment.kind}\n")
            debug_file.write(f"language={segment.language}\n")
            debug_file.write(f"voice_id={segment.voice_id or 'default'}\n")
            debug_file.write(f"section_type={segment.section_type}\n")
            debug_file.write(f"pause_after={segment.pause_after}\n")
            debug_file.write(f"language_source={segment.language_source}\n")
            debug_file.write(f"detection_confident={segment.detection_confident}\n")
            debug_file.write(f"detection_score={segment.detection_score}\n")
            debug_file.write(f"practice_mode={segment.practice_mode}\n")
            debug_file.write(f"practice_trigger={segment.practice_trigger!r}\n")
            debug_file.write(
                f"practice_pause_inserted={segment.practice_pause_inserted}\n"
            )
            debug_file.write(f"seconds={segment.seconds}\n")
            debug_file.write(f"text={segment.text!r}\n")
            debug_file.write("\n")


def write_language_detection_debug(debug_entries: list[str], debug_path: Path) -> None:
    """Write exact language detection debug blocks to disk."""

    debug_path.parent.mkdir(parents=True, exist_ok=True)
    debug_path.write_text("".join(debug_entries), encoding="utf-8")


def write_smart_cleanup_debug(
    cleanup_records: list[SmartCleanupRecord],
    segments: list[ScriptSegment],
    auto_pause_insertions: list[int],
    debug_path: Path,
) -> None:
    """Write raw PDF lines, final text units, and auto-pause positions."""

    text_segments = [segment for segment in segments if segment.kind == "text"]

    debug_path.parent.mkdir(parents=True, exist_ok=True)
    with debug_path.open("w", encoding="utf-8") as debug_file:
        debug_file.write("RAW LINES:\n")
        for record in cleanup_records:
            debug_file.write(f"{record.raw_line}\n")
        debug_file.write("\nFINAL CLEANED SEGMENTS:\n")
        for index, segment in enumerate(text_segments, start=1):
            debug_file.write(f"{index}. {segment.text}\n")
            debug_file.write(
                f"PRACTICE MODE: {'ON' if segment.practice_mode else 'OFF'}\n"
            )
            debug_file.write(f"TRIGGER:\n{segment.practice_trigger or 'none'}\n")
            debug_file.write(
                "PAUSE INSERTED:\n"
                f"{'yes' if segment.practice_pause_inserted else 'no'}\n"
            )
        debug_file.write("\nAUTO PAUSE INSERTED AFTER:\n")
        if auto_pause_insertions:
            for segment_number in auto_pause_insertions:
                debug_file.write(f"segment {segment_number}\n")
        else:
            debug_file.write("none\n")


def write_debug_text(text: str, debug_path: Path) -> None:
    """Write normalized extracted text before parsing starts."""

    debug_path.parent.mkdir(parents=True, exist_ok=True)
    debug_path.write_text(text, encoding="utf-8")


class TextToSpeechService:
    """Small wrapper around edge-tts for voice options and MP3 generation."""

    ENGLISH_VOICES: tuple[VoiceOption, ...] = (
        VoiceOption("en-US-JennyNeural", "en-US-JennyNeural", "Female"),
        VoiceOption("en-US-GuyNeural", "en-US-GuyNeural", "Male"),
        VoiceOption("en-US-AriaNeural", "en-US-AriaNeural", "Female"),
    )
    SPANISH_VOICES: tuple[VoiceOption, ...] = (
        VoiceOption("es-CO-SalomeNeural", "es-CO-SalomeNeural", "Female"),
        VoiceOption("es-CO-GonzaloNeural", "es-CO-GonzaloNeural", "Male"),
        VoiceOption("es-MX-DaliaNeural", "es-MX-DaliaNeural", "Female"),
        VoiceOption("es-MX-JorgeNeural", "es-MX-JorgeNeural", "Male"),
        VoiceOption("es-ES-ElviraNeural", "es-ES-ElviraNeural", "Female"),
        VoiceOption("es-ES-AlvaroNeural", "es-ES-AlvaroNeural", "Male"),
    )

    def get_english_voice_options(self) -> list[VoiceOption]:
        """Return the English voices exposed in the app."""

        return list(self.ENGLISH_VOICES)

    def get_spanish_voice_options(self) -> list[VoiceOption]:
        """Return the Spanish voices exposed in the app."""

        return list(self.SPANISH_VOICES)

    def save_segments_to_mp3(
        self,
        segments: list[ScriptSegment],
        output_path: Path,
        *,
        english_voice_id: str,
        spanish_voice_id: str,
        rate: int,
        volume: int,
        progress_callback: Callable[[int, int], None],
    ) -> None:
        """Generate temporary MP3 files and concatenate them into one audiobook."""

        if not segments:
            raise PDFAudiobookError("No readable text or pause tags were found.")

        asyncio.run(
            self._save_all_segments_with_edge_tts(
                segments=segments,
                output_path=output_path,
                english_voice_id=english_voice_id,
                spanish_voice_id=spanish_voice_id,
                rate=rate,
                volume=volume,
                progress_callback=progress_callback,
            )
        )

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise PDFAudiobookError(
                "The audio file was not created. Check your internet connection, "
                "try a different output folder, or try a shorter PDF."
            )

    def save_preview_to_mp3(
        self,
        output_path: Path,
        *,
        english_voice_id: str,
        spanish_voice_id: str,
        rate: int,
        volume: int,
    ) -> None:
        """Generate a short bilingual voice preview MP3."""

        segments = [
            ScriptSegment(
                kind="text",
                text="Hello. This is a sample of the selected English voice.",
                language="EN",
            ),
            ScriptSegment(
                kind="text",
                text="Hola. Esta es una muestra de la voz española seleccionada.",
                language="ES",
            ),
        ]

        asyncio.run(
            self._save_all_segments_with_edge_tts(
                segments=segments,
                output_path=output_path,
                english_voice_id=english_voice_id,
                spanish_voice_id=spanish_voice_id,
                rate=rate,
                volume=volume,
                progress_callback=lambda _current, _total: None,
            )
        )

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise PDFAudiobookError("The preview audio file was not created.")

    @staticmethod
    async def _save_all_segments_with_edge_tts(
        *,
        segments: list[ScriptSegment],
        output_path: Path,
        english_voice_id: str,
        spanish_voice_id: str,
        rate: int,
        volume: int,
        progress_callback: Callable[[int, int], None],
    ) -> None:
        """Create speech files for text segments and concatenate everything."""

        total_segments = len(segments)
        generated_speech_segments = 0
        added_pause_segments = 0
        processed_segments = 0

        print(f"total parsed segments: {total_segments}")

        with tempfile.TemporaryDirectory(
            prefix="pdf-audiobook-",
            dir=tempfile.gettempdir(),
        ) as temp_folder:
            temp_path = Path(temp_folder)

            with output_path.open("wb") as final_audio:
                for index, segment in enumerate(segments, start=1):
                    if segment.kind == "pause":
                        silence_path = temp_path / f"silence-{index:04d}.mp3"
                        TextToSpeechService._create_silence_mp3(
                            segment.seconds,
                            silence_path,
                        )
                        final_audio.write(silence_path.read_bytes())
                        added_pause_segments += 1
                        print(f"added silence segment: {segment.seconds} seconds")
                        processed_segments += 1
                        progress_callback(processed_segments, total_segments)
                        continue

                    segment_text = segment.text.strip()
                    if not segment_text:
                        processed_segments += 1
                        progress_callback(processed_segments, total_segments)
                        continue

                    voice_id = segment.voice_id or (
                        spanish_voice_id
                        if segment.language == "ES"
                        else english_voice_id
                    )
                    segment_path = temp_path / f"segment-{index:04d}.mp3"
                    print(f"Generating speech segment {index}")
                    print(f"VOICE: {voice_id}")
                    print(f"TEXT: {segment_text}")

                    communicate = edge_tts.Communicate(
                        segment_text,
                        voice_id,
                        rate=f"{rate:+d}%",
                        volume=f"{volume:+d}%",
                    )
                    await communicate.save(str(segment_path))

                    if not segment_path.exists() or segment_path.stat().st_size == 0:
                        raise PDFAudiobookError(
                            f"Audio segment {index} was not created."
                        )

                    final_audio.write(segment_path.read_bytes())
                    generated_speech_segments += 1
                    processed_segments += 1
                    progress_callback(processed_segments, total_segments)

        print(f"generated speech segments: {generated_speech_segments}")
        print(f"added pause segments: {added_pause_segments}")
        print(f"final output path: {output_path}")

    @staticmethod
    def _create_silence_mp3(seconds: int, output_path: Path) -> None:
        """Create a real silent MP3 file using ffmpeg."""

        ffmpeg_path = get_ffmpeg_path()
        command = [
            ffmpeg_path,
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=24000:cl=mono",
            "-t",
            str(seconds),
            "-q:a",
            "9",
            "-acodec",
            "libmp3lame",
            str(output_path),
        ]

        try:
            subprocess.run(
                command,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError as exc:
            raise PDFAudiobookError(FFMPEG_NOT_FOUND_MESSAGE) from exc
        except subprocess.CalledProcessError as exc:
            raise PDFAudiobookError(
                "FFmpeg could not generate a pause segment."
            ) from exc

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise PDFAudiobookError("FFmpeg created an empty pause segment.")


def play_audio_file(audio_path: Path) -> None:
    """Play an audio file with a platform-appropriate command."""

    system_name = platform.system()

    try:
        if system_name == "Darwin":
            subprocess.run(["afplay", str(audio_path)], check=True)
            return

        if system_name == "Windows":
            os.startfile(str(audio_path))  # type: ignore[attr-defined]
            time.sleep(10)
            return

        linux_players = [
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(audio_path)],
            ["mpg123", str(audio_path)],
            ["mpg321", str(audio_path)],
            ["play", str(audio_path)],
            ["paplay", str(audio_path)],
        ]
        for command in linux_players:
            if shutil.which(command[0]):
                subprocess.run(command, check=True)
                return
    except (OSError, subprocess.CalledProcessError) as exc:
        raise PDFAudiobookError(
            "The preview was created, but audio playback failed. "
            "Please check that your system can play MP3 files."
        ) from exc

    raise PDFAudiobookError(
        "The preview was created, but no supported audio player was found."
    )


class ToggleSwitch(tk.Frame):
    """Canvas-based toggle switch bound to a BooleanVar."""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        text: str,
        variable: tk.BooleanVar,
        background: str,
    ) -> None:
        super().__init__(parent, bg=background)
        self.variable = variable
        self.background = background
        self._hovered = False
        self.canvas = tk.Canvas(
            self,
            width=52,
            height=28,
            bg=background,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.grid(row=0, column=0, sticky="w")
        self.label = tk.Label(
            self,
            text=text,
            bg=background,
            fg="#E6F3FF",
            font=("Inter", 11),
            cursor="hand2",
        )
        self.label.grid(row=0, column=1, sticky="w", padx=(12, 0))

        self.canvas.bind("<Button-1>", self._toggle)
        self.label.bind("<Button-1>", self._toggle)
        for widget in (self.canvas, self.label):
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)
        self.canvas.configure(cursor="hand2")
        self.variable.trace_add("write", lambda *_args: self._draw())
        self._draw()

    def _toggle(self, _event: tk.Event) -> None:
        self.variable.set(not self.variable.get())

    def _on_enter(self, _event: tk.Event) -> None:
        self._hovered = True
        self.canvas.configure(cursor="hand2")
        self.label.configure(cursor="hand2", fg="#FFFFFF")
        self._draw()

    def _on_leave(self, _event: tk.Event) -> None:
        self._hovered = False
        self.canvas.configure(cursor="hand2")
        self.label.configure(cursor="hand2", fg="#E6F3FF")
        self._draw()

    def _draw(self) -> None:
        self.canvas.delete("all")
        enabled = self.variable.get()
        fill = "#14F1D9" if enabled else "#24364F"
        outline = "#67E8F9" if enabled else "#33445F"
        if self._hovered:
            outline = "#FFFFFF" if enabled else "#67E8F9"
        knob_x = 28 if enabled else 4
        self.canvas.create_oval(
            2,
            2,
            50,
            26,
            fill=fill,
            outline=outline,
            width=2 if self._hovered else 1,
        )
        self.canvas.create_oval(knob_x, 4, knob_x + 20, 24, fill="#E6F3FF", outline="")


class AnimatedProgressBar(tk.Canvas):
    """Dark themed progress bar with a moving highlight while active."""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        variable: tk.DoubleVar,
        background: str = "#142036",
        accent: str = "#14B8A6",
    ) -> None:
        super().__init__(
            parent,
            height=16,
            bg="#0F172A",
            highlightthickness=0,
            bd=0,
        )
        self.variable = variable
        self.track_color = background
        self.accent_color = accent
        self.highlight_color = "#67E8F9"
        self._offset = 0
        self._running = False
        self.variable.trace_add("write", lambda *_args: self._draw())
        self.bind("<Configure>", lambda _event: self._draw())
        self._draw()

    def start(self) -> None:
        self._running = True
        self._animate()

    def stop(self) -> None:
        self._running = False
        self._draw()

    def _animate(self) -> None:
        if not self._running:
            return
        self._offset = (self._offset + 7) % 40
        self._draw()
        self.after(90, self._animate)

    def _draw(self) -> None:
        self.delete("all")
        width = max(self.winfo_width(), 1)
        height = max(self.winfo_height(), 1)
        percent = max(0.0, min(float(self.variable.get()), 100.0))
        fill_width = width * (percent / 100)

        self.create_rectangle(0, 0, width, height, fill=self.track_color, outline="")
        if fill_width <= 0:
            return

        segments = max(1, int(fill_width / 10))
        start = (20, 184, 166)
        end = (34, 211, 238)
        for index in range(segments):
            ratio = index / max(segments - 1, 1)
            color = "#%02x%02x%02x" % tuple(
                round(start[channel] + (end[channel] - start[channel]) * ratio)
                for channel in range(3)
            )
            x1 = fill_width * index / segments
            x2 = fill_width * (index + 1) / segments
            self.create_rectangle(x1, 0, x2, height, fill=color, outline="")
        if self._running:
            stripe_start = self._offset - 40
            while stripe_start < fill_width:
                self.create_polygon(
                    stripe_start,
                    height,
                    stripe_start + 16,
                    height,
                    stripe_start + 32,
                    0,
                    stripe_start + 16,
                    0,
                    fill=self.highlight_color,
                    outline="",
                )
                stripe_start += 40


class PDFSelectArea(tk.Canvas):
    """Modern clickable PDF selection area."""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        browse_callback: Callable[[], None],
    ) -> None:
        super().__init__(
            parent,
            height=150,
            bg="#0F172A",
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.browse_callback = browse_callback
        self._selected_filename = ""
        self._hovered = False
        self._hover_progress = 0
        self._hover_job: str | None = None
        self.bind("<Configure>", lambda _event: self._draw())
        self.bind("<Button-1>", lambda _event: self.browse_callback())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self._draw()

    def set_selected_file(self, filename: str) -> None:
        """Show only the current selected PDF name after loading."""

        self._selected_filename = filename
        self._draw()

    def reset_state(self) -> None:
        """Redraw the current selection state."""

        self._draw()

    def _on_enter(self, _event: tk.Event) -> None:
        self._hovered = True
        self._animate_hover(100)

    def _on_leave(self, _event: tk.Event) -> None:
        self._hovered = False
        self._animate_hover(0)

    def _animate_hover(self, target: int) -> None:
        if self._hover_job is not None:
            self.after_cancel(self._hover_job)
            self._hover_job = None
        if self._hover_progress == target:
            self._draw()
            return
        step = 20 if target > self._hover_progress else -20
        self._hover_progress = max(0, min(100, self._hover_progress + step))
        self._draw()
        self._hover_job = self.after(18, lambda: self._animate_hover(target))

    def _draw(self) -> None:
        self.delete("all")
        width = max(self.winfo_width(), 1)
        height = max(self.winfo_height(), 1)
        active = bool(self._selected_filename)
        hover_ratio = self._hover_progress / 100
        glowing = self._hover_progress > 0 or active
        border = "#22D3EE" if active else "#22334F"
        if self._hover_progress:
            border = "#67E8F9"
        fill = "#102C3F" if glowing else "#0B1224"
        title = "Drop or choose a PDF"
        subtitle = "Start with a document, then EchoLearn will guide the next step."
        if self._selected_filename:
            title = self._selected_filename
            subtitle = "PDF loaded successfully"

        self.create_rectangle(
            2,
            2,
            width - 2,
            height - 2,
            fill=fill,
            outline=border,
            width=3 if glowing else 2,
            dash=(8, 5),
        )
        if glowing:
            inset = int(8 - (hover_ratio * 3))
            self.create_rectangle(
                inset,
                inset,
                width - inset,
                height - inset,
                fill="",
                outline="#164E63",
                width=1,
                dash=(6, 7),
            )
        self.create_text(
            width / 2,
            height / 2 - 48,
            text="⬆",
            fill="#22D3EE",
            font=("Inter", 22, "bold"),
        )
        self.create_text(
            width / 2,
            height / 2 - 8,
            text=title,
            fill="#E6F3FF",
            font=("Inter", 20, "bold"),
        )
        if subtitle:
            self.create_text(
                width / 2,
                height / 2 + 24,
                text=subtitle,
                fill="#8EA4BF",
                font=("Inter", 14),
            )


class CustomCursorOverlay:
    """Small premium cursor drawn in a transparent overlay window."""

    transparent_color = "#010203"

    def __init__(self, app: tk.Tk) -> None:
        self.app = app
        self.visible = False
        self.interactive = False
        self.text_mode = False
        self.current_x = 0
        self.current_y = 0
        self.target_x = 0
        self.target_y = 0
        self._motion_job: str | None = None

        self.window = tk.Toplevel(app)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.configure(bg=self.transparent_color)
        self.window.wm_attributes("-topmost", True)
        try:
            self.window.wm_attributes("-transparentcolor", self.transparent_color)
        except tk.TclError:
            try:
                self.window.wm_attributes("-alpha", 0.88)
            except tk.TclError:
                pass

        self.canvas = tk.Canvas(
            self.window,
            width=54,
            height=54,
            bg=self.transparent_color,
            highlightthickness=0,
            bd=0,
            cursor="none",
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.window.geometry("54x54+0+0")
        self._draw()

    def show(self) -> None:
        if self.text_mode:
            self.hide()
            return
        if not self.visible:
            self.visible = True
            self.window.deiconify()
        self._draw()

    def hide(self) -> None:
        self.visible = False
        self.window.withdraw()

    def destroy(self) -> None:
        if self._motion_job is not None:
            self.app.after_cancel(self._motion_job)
            self._motion_job = None
        try:
            self.window.destroy()
        except tk.TclError:
            pass

    def set_text_mode(self, enabled: bool) -> None:
        self.text_mode = enabled
        if enabled:
            self.hide()
        else:
            self.show()

    def set_interactive(self, enabled: bool) -> None:
        self.interactive = enabled
        if self.visible:
            self._draw()

    def move_to(self, root_x: int, root_y: int) -> None:
        if self.text_mode:
            self.hide()
            return
        self.target_x = root_x
        self.target_y = root_y
        self.show()
        if self._motion_job is None:
            self._animate()

    def _animate(self) -> None:
        dx = self.target_x - self.current_x
        dy = self.target_y - self.current_y
        self.current_x += int(dx * 0.38) if abs(dx) > 1 else dx
        self.current_y += int(dy * 0.38) if abs(dy) > 1 else dy
        self.window.geometry(f"54x54+{self.current_x - 27}+{self.current_y - 27}")
        if abs(dx) > 1 or abs(dy) > 1:
            self._motion_job = self.app.after(12, self._animate)
        else:
            self._motion_job = None

    def _draw(self) -> None:
        self.canvas.delete("all")
        ring = 19 if self.interactive else 13
        dot = 5 if self.interactive else 4
        ring_color = "#67E8F9" if self.interactive else "#164E63"
        dot_color = "#22D3EE" if self.interactive else "#14B8A6"
        self.canvas.create_oval(
            27 - ring,
            27 - ring,
            27 + ring,
            27 + ring,
            outline=ring_color,
            width=2 if self.interactive else 1,
        )
        self.canvas.create_oval(
            27 - dot,
            27 - dot,
            27 + dot,
            27 + dot,
            fill=dot_color,
            outline="",
        )


class SplashScreen(tk.Toplevel):
    """Short startup splash screen shown before the main window."""

    def __init__(self, parent: tk.Tk, *, on_complete: Callable[[], None]) -> None:
        super().__init__(parent)
        self.on_complete = on_complete
        self.logo_image: ImageTk.PhotoImage | None = self._load_logo_image()

        self.overrideredirect(True)
        self.configure(bg="#060B1A")
        try:
            self.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        self.resizable(False, False)

        width = 420
        height = 300
        self._center(width, height)

        panel = tk.Canvas(
            self,
            width=width,
            height=height,
            bg="#060B1A",
            highlightthickness=0,
            bd=0,
        )
        panel.pack(fill=tk.BOTH, expand=True)
        self._draw_panel(panel, width, height)

        content = tk.Frame(panel, bg="#0F172A")
        panel.create_window(width / 2, height / 2, window=content)

        if self.logo_image is not None:
            tk.Label(content, image=self.logo_image, bg="#0F172A").pack(
                pady=(0, 14)
            )

        tk.Label(
            content,
            text=APP_TITLE,
            bg="#0F172A",
            fg="#E6F3FF",
            font=("Inter", 26, "bold"),
        ).pack()
        tk.Label(
            content,
            text="Learn by Listening",
            bg="#0F172A",
            fg="#8EA4BF",
            font=("Inter", 13),
        ).pack(pady=(4, 16))
        tk.Label(
            content,
            text="Loading your audio workspace...",
            bg="#0F172A",
            fg="#22D3EE",
            font=("Inter", 10),
        ).pack()

        self.lift()
        self._fade_in_step(0)
        self.after(2000, self._finish)

    def _load_logo_image(self) -> ImageTk.PhotoImage | None:
        logo_path = asset_path(LOGO_FILE)
        if not logo_path.exists():
            return None

        try:
            with Image.open(logo_path) as logo:
                resized_logo = logo.convert("RGBA").resize(
                    (96, 96),
                    Image.Resampling.LANCZOS,
                )
                return ImageTk.PhotoImage(resized_logo)
        except (OSError, tk.TclError):
            return None

    def _center(self, width: int, height: int) -> None:
        self.update_idletasks()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _draw_panel(self, canvas: tk.Canvas, width: int, height: int) -> None:
        margin = 10
        radius = 28
        x1 = margin
        y1 = margin
        x2 = width - margin
        y2 = height - margin
        points = [
            x1 + radius,
            y1,
            x2 - radius,
            y1,
            x2,
            y1,
            x2,
            y1 + radius,
            x2,
            y2 - radius,
            x2,
            y2,
            x2 - radius,
            y2,
            x1 + radius,
            y2,
            x1,
            y2,
            x1,
            y2 - radius,
            x1,
            y1 + radius,
            x1,
            y1,
        ]
        canvas.create_polygon(
            points,
            smooth=True,
            fill="#0F172A",
            outline="#1E3A5F",
            width=1,
        )
        canvas.create_oval(58, 42, width - 58, height - 42, outline="#164E63", width=1)
        canvas.create_arc(34, 18, width - 34, height - 18, start=16, extent=62, outline="#22D3EE", width=2, style=tk.ARC)

    def _fade_in_step(self, step: int) -> None:
        """Fade the splash in gently on startup."""

        try:
            self.attributes("-alpha", min(0.98, step / 12))
        except tk.TclError:
            return
        if step < 12:
            self.after(35, lambda: self._fade_in_step(step + 1))

    def _finish(self) -> None:
        try:
            self.destroy()
        finally:
            self.on_complete()


class PDFAudiobookApp(tk.Tk):
    """Main Tkinter window for the PDF audiobook converter."""

    def __init__(self) -> None:
        super().__init__()
        self.withdraw()
        self.title(APP_TITLE)
        self.geometry("1080x760")
        self.minsize(760, 560)

        self.pdf_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.page_count = tk.StringVar(value="Pages: 0")
        self.status_text = tk.StringVar(value="Choose a PDF to begin.")
        self.default_output_folder = tk.StringVar()
        self.theme_preference = tk.StringVar(value=DEFAULT_THEME_PREFERENCE)
        self.remember_last_selected_mode = tk.BooleanVar(
            value=DEFAULT_REMEMBER_LAST_SELECTED_MODE
        )
        self.selected_english_voice = tk.StringVar(value=DEFAULT_ENGLISH_VOICE)
        self.selected_spanish_voice = tk.StringVar(value=DEFAULT_SPANISH_VOICE)
        self.selected_speaker_1_voice = tk.StringVar(value=DEFAULT_ENGLISH_VOICE)
        self.selected_speaker_2_voice = tk.StringVar(value=DEFAULT_SPANISH_VOICE)
        self.rate = tk.IntVar(value=DEFAULT_RATE)
        self.volume = tk.IntVar(value=DEFAULT_VOLUME)
        self.selected_rate_label = tk.StringVar(value="Normal")
        self.selected_volume_label = tk.StringVar(value="Normal")
        self.auto_learning_pauses = tk.BooleanVar(
            value=DEFAULT_AUTO_LEARNING_PAUSES_ENABLED
        )
        self.selected_auto_pause_label = tk.StringVar(value="3 seconds")
        self.auto_pause_seconds = tk.IntVar(value=DEFAULT_AUTO_PAUSE_SECONDS)
        self.selected_auto_pause_segmentation = tk.StringVar(value="Paragraph")
        self.selected_conversion_mode = tk.StringVar(value="Audiobook")
        self.echolesson_generation_mode = tk.StringVar(
            value=DEFAULT_ECHOLESSON_GENERATION_MODE
        )
        self.conversion_mode_description = tk.StringVar(
            value=AUDIOBOOK_MODE_DESCRIPTION
        )
        self.lesson_comparison_summary = tk.StringVar(
            value=self._format_lesson_comparison_summary("", "")
        )
        self.lesson_analysis_dashboard = tk.StringVar(
            value="Choose a PDF in EchoLesson Mode to see a content summary."
        )
        self.auto_detect_language = tk.BooleanVar(value=DEFAULT_AUTO_DETECT_LANGUAGE)
        self.default_untagged_language = tk.StringVar(
            value=language_name(DEFAULT_UNTAGGED_LANGUAGE)
        )
        self.open_audio_when_finished = tk.BooleanVar(value=False)
        self.openai_api_key_placeholder = tk.StringVar()
        self.progress_value = tk.DoubleVar(value=0)
        self.progress_percent = tk.StringVar(value="0%")

        self._messages: queue.Queue[ProgressMessage] = queue.Queue()
        self._english_voice_options: list[VoiceOption] = []
        self._spanish_voice_options: list[VoiceOption] = []
        self._is_processing = False
        self._last_output_path: Path | None = None
        self._last_input_folder = ""
        self._last_output_folder = ""
        self._is_loading_settings = False
        self.logo_image: ImageTk.PhotoImage | None = None
        self.custom_cursor: CustomCursorOverlay | None = None

        self._configure_style()
        self._build_ui()
        self._setup_custom_cursor()
        self._load_voices()
        self._load_settings()
        self._attach_settings_traces()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._process_worker_messages)

    def _configure_style(self) -> None:
        """Apply a polished futuristic dark desktop theme."""

        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        app_font = ("Inter", 11)
        self.configure(bg="#060B1A")

        style.configure("App.TFrame", background="#060B1A")
        style.configure("App.TLabel", background="#060B1A")
        style.configure("Card.TFrame", background="#0F172A")
        style.configure("Panel.TFrame", background="#0B1224")
        style.configure(
            "TLabel",
            background="#0F172A",
            foreground="#E6F3FF",
            padding=(0, 3),
            font=("Inter", 15),
        )
        style.configure(
            "Muted.TLabel",
            background="#0F172A",
            foreground="#8EA4BF",
            font=("Inter", 14),
        )
        style.configure(
            "Title.TLabel",
            background="#060B1A",
            foreground="#E6F3FF",
            font=("Inter", 44, "bold"),
            padding=(0, 0),
        )
        style.configure(
            "Subtitle.TLabel",
            background="#060B1A",
            foreground="#8EA4BF",
            font=("Inter", 17),
            padding=(0, 0),
        )
        style.configure(
            "Section.TLabel",
            background="#0F172A",
            foreground="#E6F3FF",
            font=("Inter", 25, "bold"),
            padding=(0, 0),
        )
        style.configure(
            "Step.TLabel",
            background="#0F172A",
            foreground="#22D3EE",
            font=("Inter", 13, "bold"),
            padding=(0, 0),
        )
        style.configure(
            "Status.TLabel",
            background="#060B1A",
            foreground="#22C55E",
            font=("Inter", 10),
        )
        style.configure(
            "TButton",
            background="#142036",
            foreground="#E6F3FF",
            borderwidth=0,
            focusthickness=0,
            padding=(14, 9),
            font=("Inter", 11, "bold"),
        )
        style.map(
            "TButton",
            background=[("disabled", "#0B1224"), ("active", "#1E3A5F")],
            foreground=[("disabled", "#52637A"), ("active", "#FFFFFF")],
        )
        style.configure(
            "Primary.TButton",
            background="#14F1D9",
            foreground="#031B24",
            padding=(22, 13),
            font=("Inter", 13, "bold"),
        )
        style.map(
            "Primary.TButton",
            background=[("disabled", "#164E63"), ("active", "#22D3EE")],
            foreground=[("disabled", "#8EA4BF"), ("active", "#031B24")],
        )
        style.configure(
            "TEntry",
            fieldbackground="#0B1224",
            foreground="#E6F3FF",
            insertcolor="#22D3EE",
            bordercolor="#1E3A5F",
            lightcolor="#1E3A5F",
            darkcolor="#1E3A5F",
            padding=(10, 8),
        )
        style.configure(
            "TCombobox",
            fieldbackground="#0B1224",
            background="#142036",
            foreground="#E6F3FF",
            bordercolor="#1E3A5F",
            arrowcolor="#22D3EE",
            padding=(8, 7),
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", "#0B1224"), ("active", "#102C3F")],
            foreground=[("readonly", "#E6F3FF")],
            selectbackground=[("readonly", "#0B1224")],
            selectforeground=[("readonly", "#E6F3FF")],
        )
        style.configure(
            "TRadiobutton",
            background="#0F172A",
            foreground="#E6F3FF",
            padding=(0, 4),
            font=("Inter", 11),
        )
        style.map(
            "TRadiobutton",
            background=[("active", "#0F172A")],
            foreground=[("active", "#22D3EE")],
        )
        style.configure(
            "Horizontal.TProgressbar",
            background="#14B8A6",
            troughcolor="#142036",
            bordercolor="#142036",
            lightcolor="#14B8A6",
            darkcolor="#14B8A6",
            thickness=12,
        )
        style.configure(
            "Echo.Vertical.TScrollbar",
            background="#142036",
            troughcolor="#060B1A",
            bordercolor="#060B1A",
            arrowcolor="#22D3EE",
            lightcolor="#1E3A5F",
            darkcolor="#0B1224",
            width=14,
        )
        style.map(
            "Echo.Vertical.TScrollbar",
            background=[("active", "#1E3A5F"), ("pressed", "#164E63")],
            arrowcolor=[("active", "#67E8F9")],
        )

    def _load_logo_image(self) -> ImageTk.PhotoImage | None:
        """Load a compact header logo from the app assets folder."""

        logo_path = asset_path(LOGO_FILE)
        if not logo_path.exists():
            return None

        try:
            with Image.open(logo_path) as logo:
                resized_logo = logo.convert("RGBA").resize(
                    (64, 64),
                    Image.Resampling.LANCZOS,
                )
                return ImageTk.PhotoImage(resized_logo)
        except (OSError, tk.TclError):
            return None

    def _build_ui(self) -> None:
        """Create all visual controls."""

        container = ttk.Frame(self, padding=(28, 24), style="App.TFrame")
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)

        header = ttk.Frame(container, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 22))
        header.columnconfigure(1, weight=1)

        self.logo_image = self._load_logo_image()
        if self.logo_image is not None:
            self.iconphoto(True, self.logo_image)
            self.logo_shell = tk.Frame(
                header,
                bg="#0F172A",
                padx=10,
                pady=10,
                highlightthickness=1,
                highlightbackground="#1E3A5F",
            )
            self.logo_shell.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 16))
            tk.Label(
                self.logo_shell,
                image=self.logo_image,
                bg="#0F172A",
            ).pack()

        ttk.Label(header, text=APP_TITLE, style="Title.TLabel").grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(header, text="Learn by Listening", style="Subtitle.TLabel").grid(
            row=1, column=1, sticky="w", pady=(5, 0)
        )
        header_actions = ttk.Frame(header, style="App.TFrame")
        header_actions.grid(row=0, column=2, rowspan=2, sticky="e", padx=(18, 0))
        ttk.Button(
            header_actions,
            text="Settings",
            command=self._open_settings_modal,
        ).grid(row=0, column=0, sticky="e", pady=(0, 8))
        self.header_orbit = tk.Canvas(
            header_actions,
            width=170,
            height=62,
            bg="#060B1A",
            highlightthickness=0,
            bd=0,
        )
        self.header_orbit.grid(row=1, column=0, sticky="e")
        self._draw_header_orbit()
        self._start_logo_pulse()

        scroll_area = ttk.Frame(container, style="App.TFrame")
        scroll_area.grid(row=1, column=0, sticky="nsew")
        scroll_area.columnconfigure(0, weight=1)
        scroll_area.rowconfigure(0, weight=1)

        self.content_canvas = tk.Canvas(
            scroll_area,
            bg="#060B1A",
            highlightthickness=0,
            bd=0,
        )
        self.content_canvas.grid(row=0, column=0, sticky="nsew")

        content = ttk.Frame(self.content_canvas, style="App.TFrame")
        self.content_window = self.content_canvas.create_window(
            (0, 0),
            window=content,
            anchor="nw",
        )
        content.bind("<Configure>", self._update_scroll_region)
        self.content_canvas.bind("<Configure>", self._resize_scroll_content)

        content.columnconfigure(0, weight=1)

        self.mode_card = self._create_card(content)
        self.mode_card.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        self.mode_card.columnconfigure(0, weight=1)
        self.mode_card.columnconfigure(1, weight=1)
        self._add_card_header(
            self.mode_card,
            "Step 1",
            "Choose Experience",
            "Audiobook or structured learning audio",
        )

        self.audiobook_mode_card = self._create_mode_option(
            self.mode_card,
            mode_label="Audiobook",
            title="Audiobook",
            description="Convert PDF into natural audio.",
        )
        self.audiobook_mode_card.grid(
            row=1,
            column=0,
            sticky="nsew",
            pady=(18, 0),
            padx=(0, 10),
        )
        self.echolesson_mode_card = self._create_mode_option(
            self.mode_card,
            mode_label="EchoLesson",
            title="EchoLesson",
            description="Transform content into learning audio.",
        )
        self.echolesson_mode_card.grid(
            row=1,
            column=1,
            sticky="nsew",
            pady=(18, 0),
            padx=(10, 0),
        )
        self.mode_description_label = ttk.Label(
            self.mode_card,
            textvariable=self.conversion_mode_description,
            style="Muted.TLabel",
            wraplength=720,
        )
        self.mode_description_label.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(16, 0),
        )

        self.pdf_card = self._create_card(content)
        self.pdf_card.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        self.pdf_card.columnconfigure(0, weight=1)
        self.pdf_card.columnconfigure(1, weight=0)
        self._add_card_header(
            self.pdf_card,
            "Step 2",
            "Upload PDF",
            "Choose the document you want to turn into audio",
        )

        self.pdf_select_area = PDFSelectArea(
            self.pdf_card,
            browse_callback=self._choose_pdf,
        )
        self.pdf_select_area.grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(18, 10)
        )
        ttk.Entry(self.pdf_card, textvariable=self.pdf_path).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(0, 10)
        )
        ttk.Button(self.pdf_card, text="Choose PDF", command=self._choose_pdf).grid(
            row=3, column=0, sticky="w"
        )
        ttk.Label(self.pdf_card, textvariable=self.page_count, style="Muted.TLabel").grid(
            row=3, column=1, sticky="e"
        )
        self.content_summary_card = tk.Frame(
            self.pdf_card,
            bg="#0B1224",
            padx=18,
            pady=16,
            highlightthickness=1,
            highlightbackground="#1E3A5F",
        )
        self.content_summary_card.grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(16, 0),
        )
        self.content_summary_card.columnconfigure(0, weight=1)
        tk.Label(
            self.content_summary_card,
            text="Content Summary",
            bg="#0B1224",
            fg="#E6F3FF",
            font=("Inter", 18, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            self.content_summary_card,
            textvariable=self.lesson_analysis_dashboard,
            bg="#0B1224",
            fg="#8EA4BF",
            font=("Inter", 14),
            justify=tk.LEFT,
            wraplength=760,
        ).grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.content_summary_card.grid_remove()

        # Hidden internal buffers preserve EchoLesson functionality without
        # exposing implementation markup in the consumer UI.
        self.lesson_structure_preview = tk.Text(
            self,
            height=1,
            width=1,
        )
        self.lesson_structure_preview_b = tk.Text(
            self,
            height=1,
            width=1,
        )

        self.conversion_card = self._create_card(content)
        self.conversion_card.grid(row=2, column=0, sticky="ew", pady=(0, 0))
        self.conversion_card.columnconfigure(0, weight=1)
        self.conversion_card.columnconfigure(1, weight=0)
        self._add_card_header(
            self.conversion_card,
            "Step 3",
            "Generate Audio",
            "Create the final listening file",
        )

        ttk.Label(
            self.conversion_card,
            text="Save audio as",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(18, 0))
        ttk.Entry(self.conversion_card, textvariable=self.output_path).grid(
            row=2, column=0, sticky="ew", pady=(6, 10), padx=(0, 8)
        )
        ttk.Button(
            self.conversion_card,
            text="Save As",
            command=self._choose_output,
        ).grid(row=2, column=1, sticky="e", pady=(6, 10))

        self.progress_bar = AnimatedProgressBar(
            self.conversion_card,
            variable=self.progress_value,
        )
        self.progress_bar.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 8))

        progress_meta = ttk.Frame(self.conversion_card, style="Card.TFrame")
        progress_meta.grid(row=4, column=0, columnspan=2, sticky="ew")
        progress_meta.columnconfigure(0, weight=1)
        ttk.Label(
            progress_meta,
            text="Current task",
            style="Muted.TLabel",
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            progress_meta,
            textvariable=self.progress_percent,
            style="Section.TLabel",
        ).grid(row=0, column=1, sticky="e")

        ttk.Label(
            self.conversion_card,
            textvariable=self.status_text,
            style="Muted.TLabel",
            wraplength=720,
        ).grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(6, 12)
        )

        ToggleSwitch(
            self.conversion_card,
            text="Open audio automatically when finished",
            variable=self.open_audio_when_finished,
            background="#0F172A",
        ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(0, 10))

        action_row = ttk.Frame(self.conversion_card, style="Card.TFrame")
        action_row.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        action_row.columnconfigure(0, weight=1)
        action_row.columnconfigure(1, weight=1)

        self.open_audio_button = ttk.Button(
            action_row,
            text="Open Audio",
            command=self._open_last_audio,
        )
        self.open_audio_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.open_audio_button.configure(state=tk.DISABLED)

        self.reveal_mp3_button = ttk.Button(
            action_row,
            text="Reveal MP3",
            command=self._reveal_last_mp3,
        )
        self.reveal_mp3_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self.reveal_mp3_button.configure(state=tk.DISABLED)

        self.convert_button = ttk.Button(
            self.conversion_card,
            text="Generate Audio",
            style="Primary.TButton",
            command=self._start_conversion,
        )
        self.convert_button.grid(row=8, column=0, columnspan=2, sticky="ew")

        self._update_lesson_comparison_summary()
        self._refresh_mode_cards()
        self._sync_lesson_builder_visibility()
        self._bind_scroll_events(self)
        self._apply_interactive_cursors(self)

    def _open_settings_modal(self) -> None:
        """Open app preferences and future configuration placeholders."""

        if hasattr(self, "_settings_window") and self._settings_window.winfo_exists():
            self._settings_window.lift()
            self._settings_window.focus_force()
            return

        modal = tk.Toplevel(self)
        self._settings_window = modal
        modal.title("EchoLearn Settings")
        modal.configure(bg="#060B1A")
        modal.geometry("860x620")
        modal.minsize(640, 440)
        modal.transient(self)
        modal.protocol("WM_DELETE_WINDOW", lambda: self._close_settings_modal(modal))

        shell = ttk.Frame(modal, padding=(24, 22), style="App.TFrame")
        shell.pack(fill=tk.BOTH, expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(2, weight=1)

        ttk.Label(shell, text="Settings", style="Section.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            shell,
            text="Local preferences and future configuration placeholders.",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 16))

        settings_body = ttk.Frame(shell, style="App.TFrame")
        settings_body.grid(row=2, column=0, sticky="nsew")
        settings_body.columnconfigure(1, weight=1)
        settings_body.rowconfigure(0, weight=1)

        nav = tk.Frame(
            settings_body,
            bg="#0B1224",
            padx=10,
            pady=10,
            highlightthickness=1,
            highlightbackground="#1E3A5F",
        )
        nav.grid(row=0, column=0, sticky="nsw", padx=(0, 14))
        nav.grid_propagate(False)
        nav.configure(width=172)

        self._settings_selected_category = tk.StringVar(value="General")
        self._settings_nav_items: dict[str, tk.Frame] = {}
        self._settings_nav_labels: dict[str, tk.Label] = {}
        for row, category in enumerate(("General", "Audio", "EchoLesson", "Advanced")):
            item = self._create_settings_nav_item(nav, category)
            item.grid(row=row, column=0, sticky="ew", pady=(0, 6))
            self._settings_nav_items[category] = item

        content_shell = tk.Frame(
            settings_body,
            bg="#0F172A",
            padx=20,
            pady=18,
            highlightthickness=1,
            highlightbackground="#1E3A5F",
        )
        content_shell.grid(row=0, column=1, sticky="nsew")
        content_shell.columnconfigure(0, weight=1)
        content_shell.rowconfigure(2, weight=1)

        self._settings_section_title = tk.StringVar()
        self._settings_section_description = tk.StringVar()
        tk.Label(
            content_shell,
            textvariable=self._settings_section_title,
            bg="#0F172A",
            fg="#E6F3FF",
            font=("Inter", 24, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            content_shell,
            textvariable=self._settings_section_description,
            bg="#0F172A",
            fg="#8EA4BF",
            font=("Inter", 13),
            justify=tk.LEFT,
            wraplength=520,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        scroll_area = ttk.Frame(content_shell, style="Card.TFrame")
        scroll_area.grid(row=2, column=0, sticky="nsew", pady=(16, 0))
        scroll_area.columnconfigure(0, weight=1)
        scroll_area.rowconfigure(0, weight=1)

        settings_canvas = tk.Canvas(
            scroll_area,
            bg="#0F172A",
            highlightthickness=0,
            bd=0,
        )
        settings_canvas.grid(row=0, column=0, sticky="nsew")
        settings_scrollbar = ttk.Scrollbar(
            scroll_area,
            orient=tk.VERTICAL,
            command=settings_canvas.yview,
            style="Echo.Vertical.TScrollbar",
        )
        settings_canvas.configure(yscrollcommand=settings_scrollbar.set)

        body = ttk.Frame(settings_canvas, style="Card.TFrame")
        body.columnconfigure(0, weight=1)
        settings_window = settings_canvas.create_window(
            (0, 0),
            window=body,
            anchor="nw",
        )
        settings_canvas.bind(
            "<Configure>",
            lambda event: self._resize_settings_scroll_content(
                settings_canvas,
                settings_window,
                event,
            ),
        )
        body.bind(
            "<Configure>",
            lambda _event: self._update_settings_scroll_region(settings_canvas),
        )
        self._settings_content_frame = body
        self._settings_canvas = settings_canvas
        self._settings_scrollbar = settings_scrollbar
        self._select_settings_category("General")

        button_row = ttk.Frame(shell, style="App.TFrame")
        button_row.grid(row=3, column=0, sticky="ew", pady=(18, 0))
        button_row.columnconfigure(0, weight=1)
        ttk.Button(
            button_row,
            text="Save",
            command=lambda: self._close_settings_modal(modal),
        ).grid(row=0, column=1, sticky="e")

        self._bind_settings_scroll_events(modal, settings_canvas)
        self._apply_interactive_cursors(modal)
        modal.focus_force()

    def _create_settings_nav_item(self, parent: tk.Widget, category: str) -> tk.Frame:
        """Create one clickable Settings category item."""

        item = tk.Frame(
            parent,
            bg="#0B1224",
            padx=12,
            pady=10,
            cursor=self._interactive_cursor(),
        )
        label = tk.Label(
            item,
            text=category,
            bg="#0B1224",
            fg="#8EA4BF",
            font=("Inter", 13, "bold"),
            anchor="w",
            cursor=self._interactive_cursor(),
        )
        label.pack(fill=tk.X)
        self._settings_nav_labels[category] = label
        for widget in (item, label):
            widget.bind(
                "<Button-1>",
                lambda _event, selected=category: self._select_settings_category(
                    selected
                ),
            )
            widget.bind("<Enter>", self._on_interactive_cursor_enter, add="+")
            widget.bind("<Leave>", self._on_interactive_cursor_leave, add="+")
        return item

    def _select_settings_category(self, category: str) -> None:
        """Switch the Settings right panel to the selected category."""

        self._settings_selected_category.set(category)
        self._refresh_settings_nav()
        for child in self._settings_content_frame.winfo_children():
            child.destroy()

        descriptions = {
            "General": "Defaults that shape how EchoLearn opens and remembers your workflow.",
            "Audio": "Voice, speed, and volume defaults used automatically when generating audio.",
            "EchoLesson": "Lesson-building preferences for structured learning audio.",
            "Advanced": "Future AI and export configuration placeholders.",
        }
        self._settings_section_title.set(category)
        self._settings_section_description.set(descriptions[category])

        if category == "General":
            self._build_general_settings(self._settings_content_frame)
        elif category == "Audio":
            self._build_audio_settings(self._settings_content_frame)
        elif category == "EchoLesson":
            self._build_echolesson_settings(self._settings_content_frame)
        else:
            self._build_advanced_settings(self._settings_content_frame)

        self._settings_content_frame.update_idletasks()
        self._settings_canvas.yview_moveto(0)
        self._update_settings_scroll_region(self._settings_canvas)
        self._apply_interactive_cursors(self._settings_window)

    def _refresh_settings_nav(self) -> None:
        """Update Settings category highlight state."""

        selected = self._settings_selected_category.get()
        for category, item in self._settings_nav_items.items():
            active = category == selected
            bg = "#0B2F35" if active else "#0B1224"
            fg = "#E6F3FF" if active else "#8EA4BF"
            item.configure(bg=bg, highlightthickness=1 if active else 0)
            if active:
                item.configure(highlightbackground="#22D3EE")
            self._settings_nav_labels[category].configure(bg=bg, fg=fg)

    def _build_general_settings(self, parent: tk.Widget) -> None:
        card = self._create_settings_section(parent, "Workflow Defaults", 0)
        self._add_folder_setting_row(card, 1)
        self._add_combobox_setting_row(
            card,
            2,
            "Theme preference",
            self.theme_preference,
            list(THEME_OPTIONS),
        )
        ToggleSwitch(
            card,
            text="Remember last selected mode",
            variable=self.remember_last_selected_mode,
            background="#0F172A",
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(12, 0))

    def _build_audio_settings(self, parent: tk.Widget) -> None:
        card = self._create_settings_section(parent, "Audio Defaults", 0)
        self._add_combobox_setting_row(
            card,
            1,
            "Default English audiobook voice",
            self.selected_english_voice,
            [option.label for option in self._english_voice_options]
            or [DEFAULT_ENGLISH_VOICE],
        )
        self._add_combobox_setting_row(
            card,
            2,
            "Default Spanish audiobook voice",
            self.selected_spanish_voice,
            [option.label for option in self._spanish_voice_options]
            or [DEFAULT_SPANISH_VOICE],
        )
        self._add_combobox_setting_row(
            card,
            3,
            "Default speaker 1 voice",
            self.selected_speaker_1_voice,
            [option.label for option in self._all_voice_options()]
            or [DEFAULT_ENGLISH_VOICE],
        )
        self._add_combobox_setting_row(
            card,
            4,
            "Default speaker 2 voice",
            self.selected_speaker_2_voice,
            [option.label for option in self._all_voice_options()]
            or [DEFAULT_SPANISH_VOICE],
        )
        self._add_combobox_setting_row(
            card,
            5,
            "Default speed",
            self.selected_rate_label,
            list(RATE_OPTIONS),
            on_select=self._update_rate_from_label,
        )
        self._add_combobox_setting_row(
            card,
            6,
            "Default volume",
            self.selected_volume_label,
            list(VOLUME_OPTIONS),
            on_select=self._update_volume_from_label,
        )

        language_card = self._create_settings_section(parent, "Language & Pauses", 1)
        ToggleSwitch(
            language_card,
            text="Auto-detect language",
            variable=self.auto_detect_language,
            background="#0F172A",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(12, 0))
        self._add_combobox_setting_row(
            language_card,
            2,
            "Default language for untagged text",
            self.default_untagged_language,
            ["English", "Spanish"],
        )
        ToggleSwitch(
            language_card,
            text="Auto Learning Pauses",
            variable=self.auto_learning_pauses,
            background="#0F172A",
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(12, 0))
        self._add_combobox_setting_row(
            language_card,
            4,
            "Auto pause duration",
            self.selected_auto_pause_label,
            list(AUTO_PAUSE_OPTIONS),
            on_select=self._update_auto_pause_from_label,
        )
        self._add_combobox_setting_row(
            language_card,
            5,
            "Auto pause by",
            self.selected_auto_pause_segmentation,
            list(AUTO_PAUSE_SEGMENTATION_OPTIONS),
        )

    def _build_echolesson_settings(self, parent: tk.Widget) -> None:
        card = self._create_settings_section(parent, "Lesson Generation Mode", 0)
        tk.Label(
            card,
            text="Choose how EchoLearn should prepare structured lessons.",
            bg="#0F172A",
            fg="#8EA4BF",
            font=("Inter", 13),
            justify=tk.LEFT,
            wraplength=540,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(10, 4))
        ttk.Radiobutton(
            card,
            text="Standard",
            value="Standard",
            variable=self.echolesson_generation_mode,
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(12, 0))
        ttk.Radiobutton(
            card,
            text="AI Enhanced",
            value="AI Enhanced",
            variable=self.echolesson_generation_mode,
            state=tk.DISABLED,
        ).grid(row=3, column=0, sticky="w", pady=(8, 0))
        tk.Label(
            card,
            text="Coming Soon",
            bg="#0B2F35",
            fg="#67E8F9",
            font=("Inter", 11, "bold"),
            padx=10,
            pady=4,
        ).grid(row=3, column=1, sticky="w", padx=(10, 0), pady=(8, 0))
        tk.Label(
            card,
            text=(
                "AI Enhanced will use OpenAI to automatically build structured "
                "learning lessons from PDFs."
            ),
            bg="#0F172A",
            fg="#8EA4BF",
            font=("Inter", 13),
            justify=tk.LEFT,
            wraplength=540,
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(14, 0))

    def _build_advanced_settings(self, parent: tk.Widget) -> None:
        card = self._create_settings_section(parent, "Future Configuration", 0)
        self._add_placeholder_entry_row(
            card,
            1,
            "OpenAI API Key",
            self.openai_api_key_placeholder,
            "Coming Soon",
        )
        self._add_placeholder_status_row(card, 2, "Future AI Provider", "Coming Soon")
        self._add_placeholder_status_row(card, 3, "Future Export Settings", "Coming Soon")

    def _resize_settings_scroll_content(
        self,
        canvas: tk.Canvas,
        window_id: int,
        event: tk.Event,
    ) -> None:
        """Keep settings content matched to the visible scroll viewport."""

        canvas.itemconfigure(window_id, width=max(event.width, 1))
        self._update_settings_scroll_region(canvas)

    def _update_settings_scroll_region(self, canvas: tk.Canvas) -> None:
        """Update the scrollable bounds for the Settings modal."""

        canvas.configure(scrollregion=canvas.bbox("all"))
        self._sync_settings_scrollbar_visibility(canvas)

    def _sync_settings_scrollbar_visibility(self, canvas: tk.Canvas) -> None:
        """Show the Settings scrollbar only when content exceeds the viewport."""

        if not hasattr(self, "_settings_scrollbar"):
            return
        canvas.update_idletasks()
        scroll_region = canvas.bbox("all")
        if scroll_region is None:
            needs_scrollbar = False
        else:
            content_height = scroll_region[3] - scroll_region[1]
            needs_scrollbar = content_height > canvas.winfo_height() + 1

        if needs_scrollbar:
            if not self._settings_scrollbar.winfo_ismapped():
                self._settings_scrollbar.grid(
                    row=0,
                    column=1,
                    sticky="ns",
                    padx=(10, 0),
                )
        elif self._settings_scrollbar.winfo_ismapped():
            self._settings_scrollbar.grid_remove()
            canvas.yview_moveto(0)

    def _bind_settings_scroll_events(
        self,
        widget: tk.Widget,
        canvas: tk.Canvas,
    ) -> None:
        """Bind wheel and trackpad scrolling throughout the Settings modal."""

        widget.bind(
            "<MouseWheel>",
            lambda event, scroll_canvas=canvas: self._on_settings_mousewheel(
                event,
                scroll_canvas,
            ),
            add="+",
        )
        widget.bind(
            "<Button-4>",
            lambda event, scroll_canvas=canvas: self._on_settings_mousewheel(
                event,
                scroll_canvas,
            ),
            add="+",
        )
        widget.bind(
            "<Button-5>",
            lambda event, scroll_canvas=canvas: self._on_settings_mousewheel(
                event,
                scroll_canvas,
            ),
            add="+",
        )
        for child in widget.winfo_children():
            self._bind_settings_scroll_events(child, canvas)

    def _on_settings_mousewheel(
        self,
        event: tk.Event,
        canvas: tk.Canvas,
    ) -> str:
        """Scroll the Settings modal with trackpads and mouse wheels."""

        if getattr(event, "num", None) == 4:
            canvas.yview_scroll(-3, "units")
        elif getattr(event, "num", None) == 5:
            canvas.yview_scroll(3, "units")
        elif event.delta:
            scroll_units = self._scroll_units_from_delta(event.delta)
            if scroll_units:
                canvas.yview_scroll(scroll_units, "units")
        return "break"

    def _create_settings_section(
        self,
        parent: tk.Widget,
        title: str,
        row: int,
    ) -> tk.Frame:
        """Create a compact settings section inside the modal."""

        section = self._create_card(parent)
        section.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        section.columnconfigure(1, weight=1)
        ttk.Label(section, text=title, style="Section.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        return section

    def _add_combobox_setting_row(
        self,
        parent: tk.Widget,
        row: int,
        label: str,
        variable: tk.StringVar,
        values: list[str],
        *,
        on_select: Callable[[tk.Event | None], None] | None = None,
    ) -> ttk.Combobox:
        """Add one label plus combobox row to the settings modal."""

        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=(12, 0))
        combobox = ttk.Combobox(
            parent,
            textvariable=variable,
            state="readonly",
            values=values,
        )
        combobox.grid(row=row, column=1, columnspan=2, sticky="ew", padx=(12, 0), pady=(12, 0))
        if on_select is not None:
            combobox.bind("<<ComboboxSelected>>", on_select)
        return combobox

    def _add_folder_setting_row(self, parent: tk.Widget, row: int) -> None:
        """Add default output folder controls to the settings modal."""

        ttk.Label(parent, text="Default output folder").grid(
            row=row, column=0, sticky="w", pady=(12, 0)
        )
        ttk.Entry(parent, textvariable=self.default_output_folder).grid(
            row=row, column=1, sticky="ew", padx=(12, 8), pady=(12, 0)
        )
        ttk.Button(
            parent,
            text="Choose",
            command=self._choose_default_output_folder,
        ).grid(row=row, column=2, sticky="e", pady=(12, 0))

    def _choose_default_output_folder(self) -> None:
        """Choose the folder used for new MP3 output paths."""

        initial_directory = (
            self.default_output_folder.get()
            or self._last_output_folder
            or str(Path.home())
        )
        path = filedialog.askdirectory(
            title="Choose default output folder",
            initialdir=initial_directory,
        )
        if path:
            self.default_output_folder.set(path)
            self._last_output_folder = path
            self._save_settings()
            if self.pdf_path.get():
                self._set_default_output_for_pdf(Path(self.pdf_path.get()))

    def _add_placeholder_entry_row(
        self,
        parent: tk.Widget,
        row: int,
        label: str,
        variable: tk.StringVar,
        status: str,
    ) -> None:
        """Add a future setting row with a local placeholder entry."""

        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=(12, 0))
        ttk.Entry(parent, textvariable=variable, show="*").grid(
            row=row,
            column=1,
            sticky="ew",
            padx=(12, 10),
            pady=(12, 0),
        )
        self._create_status_pill(parent, status).grid(
            row=row,
            column=2,
            sticky="e",
            pady=(12, 0),
        )

    def _add_placeholder_status_row(
        self,
        parent: tk.Widget,
        row: int,
        label: str,
        status: str,
    ) -> None:
        """Add a future setting row that is intentionally not functional yet."""

        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=(12, 0))
        self._create_status_pill(parent, status).grid(
            row=row,
            column=1,
            sticky="w",
            padx=(12, 0),
            pady=(12, 0),
        )

    def _create_status_pill(self, parent: tk.Widget, text: str) -> tk.Label:
        """Create a small EchoLearn status badge."""

        return tk.Label(
            parent,
            text=text,
            bg="#0B2F35",
            fg="#67E8F9",
            font=("Inter", 11, "bold"),
            padx=10,
            pady=4,
        )

    def _close_settings_modal(self, modal: tk.Toplevel) -> None:
        """Save settings and close the settings modal."""

        self._save_settings()
        modal.destroy()

    def _create_card(self, parent: tk.Widget) -> tk.Frame:
        """Create a premium spatial card container."""

        card = tk.Frame(
            parent,
            padx=26,
            pady=24,
            bg="#0F172A",
            highlightthickness=1,
            highlightbackground="#1E3A5F",
            highlightcolor="#22D3EE",
        )
        return card

    def _draw_header_orbit(self) -> None:
        """Draw a subtle spatial audio accent in the header."""

        if not hasattr(self, "header_orbit"):
            return
        canvas = self.header_orbit
        canvas.delete("all")
        canvas.create_arc(16, 9, 150, 54, start=18, extent=246, outline="#164E63", width=1, style=tk.ARC)
        canvas.create_arc(30, 15, 138, 48, start=205, extent=92, outline="#22D3EE", width=2, style=tk.ARC)
        canvas.create_oval(116, 18, 124, 26, fill="#14F1D9", outline="")
        canvas.create_oval(38, 39, 43, 44, fill="#F97316", outline="")
        for index, height in enumerate((14, 24, 36, 26, 16)):
            x = 68 + index * 8
            y = 31 - height / 2
            canvas.create_line(x, y, x, y + height, fill="#67E8F9", width=2)

    def _start_logo_pulse(self) -> None:
        """Start a gentle logo pulse that feels like a quiet audio wave."""

        if not hasattr(self, "logo_shell"):
            return
        self._pulse_logo(True)

    def _pulse_logo(self, active: bool) -> None:
        if not hasattr(self, "logo_shell"):
            return
        self.logo_shell.configure(
            highlightbackground="#22D3EE" if active else "#1E3A5F"
        )
        self.after(1800 if active else 3200, lambda: self._pulse_logo(not active))

    def _create_mode_option(
        self,
        parent: tk.Widget,
        *,
        mode_label: str,
        title: str,
        description: str,
    ) -> tk.Frame:
        """Create a premium selectable mode card."""

        card = tk.Frame(
            parent,
            bg="#0B1224",
            padx=20,
            pady=18,
            cursor=self._interactive_cursor(),
            highlightthickness=1,
            highlightbackground="#1E3A5F",
            highlightcolor="#22D3EE",
        )
        card.columnconfigure(0, weight=1)

        title_label = tk.Label(
            card,
            text=title,
            bg="#0B1224",
            fg="#E6F3FF",
            font=("Inter", 18, "bold"),
            cursor=self._interactive_cursor(),
        )
        title_label.grid(row=0, column=0, sticky="w")

        description_label = tk.Label(
            card,
            text=description,
            bg="#0B1224",
            fg="#8EA4BF",
            font=("Inter", 14),
            cursor=self._interactive_cursor(),
            justify=tk.LEFT,
            wraplength=320,
        )
        description_label.grid(row=1, column=0, sticky="w", pady=(8, 0))

        card._title_label = title_label  # type: ignore[attr-defined]
        card._description_label = description_label  # type: ignore[attr-defined]
        card._mode_label = mode_label  # type: ignore[attr-defined]
        card._is_lifted = False  # type: ignore[attr-defined]

        for widget in (card, title_label, description_label):
            widget.bind(
                "<Button-1>",
                lambda _event, label=mode_label: self._select_conversion_mode(label),
            )
            widget.bind(
                "<Enter>",
                lambda _event, mode_card=card: self._set_mode_card_hover(mode_card, True),
            )
            widget.bind(
                "<Leave>",
                lambda _event, mode_card=card: self._set_mode_card_hover(mode_card, False),
            )

        return card

    def _set_mode_card_hover(self, card: tk.Frame, hovered: bool) -> None:
        """Apply a subtle hover state to mode cards."""

        for widget in (card, card._title_label, card._description_label):  # type: ignore[attr-defined]
            self._set_cursor(widget, self._interactive_cursor())
        if self.custom_cursor is not None:
            self.custom_cursor.set_interactive(hovered)

        if not hovered:
            self._restore_mode_card_lift(card)
            self._refresh_mode_cards()
            return

        is_selected = getattr(card, "_mode_label", "") == self.selected_conversion_mode.get()
        bg = "#103C45" if is_selected else "#102C3F"
        border = "#67E8F9"
        card.configure(bg=bg, highlightbackground=border)
        card._title_label.configure(bg=bg, fg="#FFFFFF")  # type: ignore[attr-defined]
        card._description_label.configure(bg=bg, fg="#A5F3FC")  # type: ignore[attr-defined]
        self._lift_mode_card(card)

    def _lift_mode_card(self, card: tk.Frame) -> None:
        """Nudge a mode card upward while hovered."""

        if getattr(card, "_is_lifted", False):
            return
        grid_info = card.grid_info()
        pady = grid_info.get("pady", (0, 0))
        if isinstance(pady, int):
            normal_pady = (pady, pady)
        else:
            normal_pady = pady
        card._normal_grid_pady = normal_pady  # type: ignore[attr-defined]
        top, bottom = normal_pady
        card.grid_configure(pady=(max(int(top) - 3, 0), int(bottom) + 3))
        card._is_lifted = True  # type: ignore[attr-defined]

    def _restore_mode_card_lift(self, card: tk.Frame) -> None:
        """Return a hovered mode card to its normal grid position."""

        if not getattr(card, "_is_lifted", False):
            return
        normal_pady = getattr(card, "_normal_grid_pady", None)
        if normal_pady is not None:
            card.grid_configure(pady=normal_pady)
        card._is_lifted = False  # type: ignore[attr-defined]

    def _select_conversion_mode(self, label: str) -> None:
        """Select a conversion mode from the card UI."""

        self.selected_conversion_mode.set(label)
        self._update_conversion_mode_description()

    def _refresh_mode_cards(self) -> None:
        """Update the visual selected state for mode cards."""

        if not hasattr(self, "audiobook_mode_card"):
            return

        selected = self.selected_conversion_mode.get()
        for card in (self.audiobook_mode_card, self.echolesson_mode_card):
            is_selected = getattr(card, "_mode_label", "") == selected
            bg = "#0B2F35" if is_selected else "#0B1224"
            border = "#22D3EE" if is_selected else "#1E3A5F"
            title_color = "#E6F3FF"
            body_color = "#67E8F9" if is_selected else "#8EA4BF"
            card.configure(
                bg=bg,
                highlightbackground=border,
                highlightthickness=2 if is_selected else 1,
            )
            card._title_label.configure(bg=bg, fg=title_color)  # type: ignore[attr-defined]
            card._description_label.configure(bg=bg, fg=body_color)  # type: ignore[attr-defined]
        self._refresh_mode_card_cursors()

    def _refresh_mode_card_cursors(self) -> None:
        """Keep mode-card cursors aligned with the custom cursor setting."""

        if not hasattr(self, "audiobook_mode_card"):
            return
        for card in (self.audiobook_mode_card, self.echolesson_mode_card):
            for widget in (
                card,
                card._title_label,  # type: ignore[attr-defined]
                card._description_label,  # type: ignore[attr-defined]
            ):
                self._set_cursor(widget, self._interactive_cursor())

    def _update_scroll_region(self, _event: tk.Event) -> None:
        """Keep the scrollable content region aligned with its children."""

        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))

    def _resize_scroll_content(self, event: tk.Event) -> None:
        """Resize the inner content frame to the visible canvas width."""

        self._draw_background_gradient(event.width, event.height)
        content_width = min(max(event.width - 8, 1), 980)
        content_x = max((event.width - content_width) // 2, 0)
        self.content_canvas.coords(self.content_window, content_x, 0)
        self.content_canvas.itemconfigure(self.content_window, width=content_width)
        self.content_canvas.tag_raise(self.content_window)
        self._reflow_cards(content_width)

    def _draw_background_gradient(self, width: int, height: int) -> None:
        """Draw a very subtle premium background gradient."""

        self.content_canvas.delete("background")
        steps = 36
        start = (6, 11, 26)
        end = (8, 24, 38)
        for index in range(steps):
            ratio = index / max(steps - 1, 1)
            color = "#%02x%02x%02x" % tuple(
                round(start[channel] + (end[channel] - start[channel]) * ratio)
                for channel in range(3)
            )
            y1 = int((height / steps) * index)
            y2 = int((height / steps) * (index + 1)) + 1
            self.content_canvas.create_rectangle(
                0,
                y1,
                width,
                y2,
                fill=color,
                outline="",
                tags="background",
            )
        self.content_canvas.tag_lower("background")

    def _apply_interactive_cursors(self, widget: tk.Widget) -> None:
        """Assign modern cursors based on each widget's interaction type."""

        for child in widget.winfo_children():
            self._prepare_widget_cursor(child)
            self._apply_interactive_cursors(child)

    def _setup_custom_cursor(self) -> None:
        """Create and bind the optional in-app custom cursor."""

        if not CUSTOM_CURSOR_ENABLED:
            return
        try:
            self.custom_cursor = CustomCursorOverlay(self)
        except tk.TclError:
            self.custom_cursor = None
            return

        self.bind("<Enter>", self._on_app_cursor_enter, add="+")
        self.bind("<Leave>", self._on_app_cursor_leave, add="+")
        self.bind("<Motion>", self._on_app_cursor_motion, add="+")
        self.custom_cursor.canvas.bind("<Motion>", self._on_app_cursor_motion, add="+")
        self._set_cursor(self, "none")
        self._refresh_control_cursors()
        self._refresh_mode_card_cursors()

    def _prepare_widget_cursor(self, widget: tk.Widget) -> None:
        """Attach cursor and hover behavior to a single widget."""

        if isinstance(widget, (ttk.Button, tk.Button)):
            self._set_cursor(widget, self._cursor_for_button(widget))
            widget.bind(
                "<Enter>",
                lambda _event, button=widget: self._on_button_hover(button, True),
                add="+",
            )
            widget.bind(
                "<Leave>",
                lambda _event, button=widget: self._on_button_hover(button, False),
                add="+",
            )
            return

        if isinstance(widget, (ttk.Entry, tk.Entry, tk.Text)):
            self._set_cursor(widget, "xterm")
            widget.bind("<Enter>", self._on_text_cursor_enter, add="+")
            widget.bind("<Leave>", self._on_text_cursor_leave, add="+")
            return

        if isinstance(widget, (ttk.Combobox, PDFSelectArea, ToggleSwitch)):
            self._set_cursor(widget, self._interactive_cursor())
            widget.bind("<Enter>", self._on_interactive_cursor_enter, add="+")
            widget.bind("<Leave>", self._on_interactive_cursor_leave, add="+")
            if isinstance(widget, ToggleSwitch):
                self._prepare_toggle_cursor(widget)
            return

        if CUSTOM_CURSOR_ENABLED and self.custom_cursor is not None:
            self._set_cursor(widget, "none")

    def _prepare_toggle_cursor(self, toggle: ToggleSwitch) -> None:
        """Route custom cursor behavior through toggle child widgets."""

        for child in (toggle.canvas, toggle.label):
            self._set_cursor(child, self._interactive_cursor())
            child.bind("<Enter>", self._on_interactive_cursor_enter, add="+")
            child.bind("<Leave>", self._on_interactive_cursor_leave, add="+")

    def _on_button_hover(self, button: tk.Widget, hovered: bool) -> None:
        """Keep button cursor feedback aligned with enabled/disabled state."""

        disabled = self._widget_is_disabled(button)
        self._set_cursor(button, self._cursor_for_button(button))
        if self.custom_cursor is not None:
            self.custom_cursor.set_interactive(hovered and not disabled)
        if isinstance(button, tk.Button) and not disabled:
            button.configure(relief=tk.RAISED if hovered else tk.FLAT)

    def _refresh_control_cursors(self) -> None:
        """Refresh cursor state after controls are enabled or disabled."""

        self._refresh_control_cursors_from(self)

    def _refresh_control_cursors_from(self, widget: tk.Widget) -> None:
        for child in widget.winfo_children():
            if isinstance(child, (ttk.Button, tk.Button)):
                self._set_cursor(child, self._cursor_for_button(child))
            elif isinstance(child, (ttk.Entry, tk.Entry, tk.Text)):
                self._set_cursor(child, "xterm")
            elif isinstance(child, (ttk.Combobox, PDFSelectArea, ToggleSwitch)):
                self._set_cursor(child, self._interactive_cursor())
                if isinstance(child, ToggleSwitch):
                    for toggle_child in (child.canvas, child.label):
                        self._set_cursor(toggle_child, self._interactive_cursor())
            elif CUSTOM_CURSOR_ENABLED and self.custom_cursor is not None:
                self._set_cursor(child, "none")
            self._refresh_control_cursors_from(child)

    def _cursor_for_button(self, button: tk.Widget) -> str:
        if self._widget_is_disabled(button):
            return "arrow"
        return self._interactive_cursor()

    def _interactive_cursor(self) -> str:
        return "none" if CUSTOM_CURSOR_ENABLED and self.custom_cursor is not None else "hand2"

    def _on_app_cursor_enter(self, event: tk.Event) -> None:
        if self.custom_cursor is not None:
            self.custom_cursor.move_to(event.x_root, event.y_root)

    def _on_app_cursor_leave(self, event: tk.Event) -> None:
        if self.custom_cursor is None:
            return
        x = event.x_root
        y = event.y_root
        inside = (
            self.winfo_rootx() <= x <= self.winfo_rootx() + self.winfo_width()
            and self.winfo_rooty() <= y <= self.winfo_rooty() + self.winfo_height()
        )
        if not inside:
            self.custom_cursor.hide()

    def _on_app_cursor_motion(self, event: tk.Event) -> None:
        if self.custom_cursor is not None:
            self.custom_cursor.move_to(event.x_root, event.y_root)

    def _on_interactive_cursor_enter(self, event: tk.Event) -> None:
        if self.custom_cursor is not None:
            self.custom_cursor.set_text_mode(False)
            self.custom_cursor.set_interactive(True)
            self.custom_cursor.move_to(event.x_root, event.y_root)

    def _on_interactive_cursor_leave(self, _event: tk.Event) -> None:
        if self.custom_cursor is not None:
            self.custom_cursor.set_interactive(False)

    def _on_text_cursor_enter(self, _event: tk.Event) -> None:
        if self.custom_cursor is not None:
            self.custom_cursor.set_text_mode(True)

    def _on_text_cursor_leave(self, _event: tk.Event) -> None:
        if self.custom_cursor is not None:
            self.custom_cursor.set_text_mode(False)

    @staticmethod
    def _widget_is_disabled(widget: tk.Widget) -> bool:
        try:
            if isinstance(widget, ttk.Widget):
                return bool(widget.instate(["disabled"]))
        except tk.TclError:
            pass
        try:
            return str(widget.cget("state")) == tk.DISABLED
        except tk.TclError:
            return False

    @staticmethod
    def _set_cursor(widget: tk.Widget, cursor: str) -> None:
        try:
            widget.configure(cursor=cursor)
        except tk.TclError:
            pass

    def _reflow_cards(self, width: int) -> None:
        """Keep the guided workflow comfortable at different widths."""

        if not hasattr(self, "echolesson_mode_card"):
            return

        compact = width < 760
        if compact:
            self.audiobook_mode_card.grid_configure(
                row=1,
                column=0,
                padx=0,
                pady=(18, 0),
            )
            self.echolesson_mode_card.grid_configure(
                row=2,
                column=0,
                padx=0,
                pady=(12, 0),
            )
            self.mode_description_label.grid_configure(
                row=3,
                column=0,
                columnspan=1,
            )
        else:
            self.audiobook_mode_card.grid_configure(
                row=1,
                column=0,
                padx=(0, 10),
                pady=(18, 0),
            )
            self.echolesson_mode_card.grid_configure(
                row=1,
                column=1,
                padx=(10, 0),
                pady=(18, 0),
            )
            self.mode_description_label.grid_configure(
                row=2,
                column=0,
                columnspan=2,
                pady=(16, 0),
            )
        self._sync_lesson_builder_visibility()

    def _bind_scroll_events(self, widget: tk.Widget) -> None:
        """Bind scroll events across the app content tree."""

        widget.bind("<MouseWheel>", self._on_mousewheel, add="+")
        widget.bind("<Button-4>", self._on_mousewheel, add="+")
        widget.bind("<Button-5>", self._on_mousewheel, add="+")
        for child in widget.winfo_children():
            self._bind_scroll_events(child)

    def _on_mousewheel(self, event: tk.Event) -> str:
        """Scroll the main content with the mouse wheel or trackpad."""

        if getattr(event, "num", None) == 4:
            self.content_canvas.yview_scroll(-3, "units")
        elif getattr(event, "num", None) == 5:
            self.content_canvas.yview_scroll(3, "units")
        elif event.delta:
            scroll_units = self._scroll_units_from_delta(event.delta)
            if scroll_units:
                self.content_canvas.yview_scroll(scroll_units, "units")
        return "break"

    @staticmethod
    def _scroll_units_from_delta(delta: int) -> int:
        """Normalize wheel and trackpad deltas across platforms."""

        if platform.system() == "Darwin":
            return -1 if delta > 0 else 1

        units = int(-1 * (delta / 120))
        if units == 0:
            return -1 if delta > 0 else 1
        return units

    def _add_card_header(
        self,
        parent: ttk.Frame,
        step: str,
        title: str,
        subtitle: str,
    ) -> None:
        """Add a compact futuristic step header."""

        title_frame = ttk.Frame(parent, style="Card.TFrame")
        title_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        title_frame.columnconfigure(1, weight=1)

        step_number = step.replace("Step", "").strip() or step
        step_badge = tk.Canvas(
            title_frame,
            width=48,
            height=48,
            bg="#0F172A",
            highlightthickness=0,
            bd=0,
        )
        step_badge.grid(row=0, column=0, rowspan=3, sticky="n", padx=(0, 14))
        step_badge.create_oval(2, 2, 46, 46, fill="#0B2F35", outline="#22D3EE", width=2)
        step_badge.create_oval(7, 7, 41, 41, fill="", outline="#164E63", width=1)
        step_badge.create_text(
            24,
            24,
            text=step_number,
            fill="#E6F3FF",
            font=("Inter", 15, "bold"),
        )

        ttk.Label(title_frame, text=step.upper(), style="Step.TLabel").grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(title_frame, text=title, style="Section.TLabel").grid(
            row=1, column=1, sticky="w", pady=(3, 0)
        )
        ttk.Label(title_frame, text=subtitle, style="Muted.TLabel").grid(
            row=2, column=1, sticky="w", pady=(2, 0)
        )

    def _draw_icon(self, canvas: tk.Canvas, icon_name: str) -> None:
        """Draw small section icons without external image dependencies."""

        accent = "#22D3EE"
        muted = "#8EA4BF"
        canvas.create_oval(2, 2, 46, 46, fill="#0B1224", outline="#1E3A5F", width=1)

        if icon_name == "pdf":
            canvas.create_rectangle(16, 11, 32, 36, outline=accent, width=2)
            canvas.create_line(27, 11, 32, 16, 32, 36, fill=accent, width=2)
            canvas.create_line(19, 22, 29, 22, fill=muted, width=2)
            canvas.create_line(19, 27, 29, 27, fill=muted, width=2)
        elif icon_name == "voices":
            canvas.create_oval(13, 14, 26, 27, outline=accent, width=2)
            canvas.create_arc(18, 18, 42, 42, start=315, extent=90, outline=muted, width=2)
            canvas.create_arc(13, 13, 45, 45, start=315, extent=90, outline=muted, width=2)
            canvas.create_line(19, 28, 19, 36, fill=accent, width=2)
            canvas.create_line(14, 36, 24, 36, fill=accent, width=2)
        elif icon_name == "learning":
            canvas.create_oval(12, 12, 22, 22, fill=accent, outline=accent)
            canvas.create_oval(28, 12, 38, 22, fill=muted, outline=muted)
            canvas.create_oval(20, 28, 30, 38, fill=accent, outline=accent)
            canvas.create_line(22, 18, 28, 18, fill=muted, width=2)
            canvas.create_line(18, 22, 24, 28, fill=muted, width=2)
            canvas.create_line(32, 22, 28, 28, fill=muted, width=2)
        elif icon_name == "mode":
            canvas.create_oval(13, 13, 22, 22, outline=accent, width=2)
            canvas.create_oval(26, 26, 35, 35, outline=accent, width=2)
            canvas.create_line(24, 17, 34, 17, fill=muted, width=2)
            canvas.create_line(14, 31, 24, 31, fill=muted, width=2)
            canvas.create_line(22, 22, 26, 26, fill=muted, width=2)
        elif icon_name == "builder":
            canvas.create_rectangle(14, 12, 34, 36, outline=accent, width=2)
            canvas.create_line(18, 19, 30, 19, fill=muted, width=2)
            canvas.create_line(18, 24, 30, 24, fill=muted, width=2)
            canvas.create_line(18, 29, 26, 29, fill=muted, width=2)
            canvas.create_oval(29, 29, 37, 37, outline=accent, width=2)
        else:
            canvas.create_line(14, 24, 32, 24, fill=accent, width=3, arrow=tk.LAST)
            canvas.create_arc(13, 13, 36, 36, start=220, extent=250, outline=muted, width=2)

    def _load_voices(self) -> None:
        """Load voice lists and populate both language selectors."""

        try:
            service = TextToSpeechService()
            self._english_voice_options = service.get_english_voice_options()
            self._spanish_voice_options = service.get_spanish_voice_options()
        except Exception as exc:
            traceback.print_exc()
            raise

        self.selected_english_voice.set(DEFAULT_ENGLISH_VOICE)
        self.selected_spanish_voice.set(DEFAULT_SPANISH_VOICE)
        self.selected_speaker_1_voice.set(DEFAULT_ENGLISH_VOICE)
        self.selected_speaker_2_voice.set(DEFAULT_SPANISH_VOICE)

    def _load_settings(self) -> None:
        """Load saved settings from disk, using safe defaults when absent."""

        settings_file = SETTINGS_FILE
        if not settings_file.exists() and LEGACY_SETTINGS_FILE.exists():
            settings_file = LEGACY_SETTINGS_FILE
        if not settings_file.exists():
            self._save_settings()
            return

        try:
            settings = json.loads(settings_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._save_settings()
            return
        if not isinstance(settings, dict):
            self._save_settings()
            return

        self._is_loading_settings = True
        try:
            default_output_folder = settings.get("default_output_folder", "")
            if isinstance(default_output_folder, str):
                self.default_output_folder.set(default_output_folder)

            theme_preference = str(
                settings.get("theme_preference", DEFAULT_THEME_PREFERENCE)
            )
            if theme_preference in THEME_OPTIONS:
                self.theme_preference.set(theme_preference)

            self.remember_last_selected_mode.set(
                bool(
                    settings.get(
                        "remember_last_selected_mode",
                        DEFAULT_REMEMBER_LAST_SELECTED_MODE,
                    )
                )
            )

            english_voice = str(settings.get("english_voice", ""))
            spanish_voice = str(settings.get("spanish_voice", ""))
            if english_voice in [option.label for option in self._english_voice_options]:
                self.selected_english_voice.set(english_voice)
            if spanish_voice in [option.label for option in self._spanish_voice_options]:
                self.selected_spanish_voice.set(spanish_voice)
            speaker_voice_labels = [option.label for option in self._all_voice_options()]
            speaker_1_voice = str(settings.get("speaker_1_voice", ""))
            speaker_2_voice = str(settings.get("speaker_2_voice", ""))
            if speaker_1_voice in speaker_voice_labels:
                self.selected_speaker_1_voice.set(speaker_1_voice)
            if speaker_2_voice in speaker_voice_labels:
                self.selected_speaker_2_voice.set(speaker_2_voice)

            rate_label = str(settings.get("speech_rate", ""))
            volume_label = str(settings.get("volume", ""))
            if rate_label in RATE_OPTIONS:
                self.selected_rate_label.set(rate_label)
                self._update_rate_from_label()
            if volume_label in VOLUME_OPTIONS:
                self.selected_volume_label.set(volume_label)
                self._update_volume_from_label()

            self.auto_learning_pauses.set(
                bool(
                    settings.get(
                        "auto_learning_pauses",
                        DEFAULT_AUTO_LEARNING_PAUSES_ENABLED,
                    )
                )
            )
            auto_pause_seconds = settings.get(
                "auto_pause_seconds",
                DEFAULT_AUTO_PAUSE_SECONDS,
            )
            try:
                auto_pause_seconds_value = int(auto_pause_seconds)
            except (TypeError, ValueError):
                auto_pause_seconds_value = DEFAULT_AUTO_PAUSE_SECONDS
            if auto_pause_seconds_value in AUTO_PAUSE_OPTIONS.values():
                self.auto_pause_seconds.set(auto_pause_seconds_value)
                self.selected_auto_pause_label.set(
                    self._auto_pause_label_for_seconds(auto_pause_seconds_value)
                )
            auto_pause_segmentation = str(
                settings.get(
                    "auto_pause_segmentation",
                    DEFAULT_AUTO_PAUSE_SEGMENTATION,
                )
            ).lower()
            if auto_pause_segmentation in AUTO_PAUSE_SEGMENTATION_OPTIONS.values():
                self.selected_auto_pause_segmentation.set(
                    self._auto_pause_segmentation_label_for_value(
                        auto_pause_segmentation
                    )
                )
            conversion_mode = str(settings.get("conversion_mode", DEFAULT_CONVERSION_MODE)).lower()
            if (
                self.remember_last_selected_mode.get()
                and conversion_mode in CONVERSION_MODE_OPTIONS.values()
            ):
                self.selected_conversion_mode.set(
                    self._conversion_mode_label_for_value(conversion_mode)
                )
                self._update_conversion_mode_description()
            else:
                self.selected_conversion_mode.set(
                    self._conversion_mode_label_for_value(DEFAULT_CONVERSION_MODE)
                )
                self._update_conversion_mode_description()

            echolesson_generation_mode = str(
                settings.get(
                    "echolesson_generation_mode",
                    DEFAULT_ECHOLESSON_GENERATION_MODE,
                )
            )
            if echolesson_generation_mode == "AI Enhanced":
                echolesson_generation_mode = DEFAULT_ECHOLESSON_GENERATION_MODE
            if echolesson_generation_mode in ECHOLESSON_GENERATION_MODE_OPTIONS:
                self.echolesson_generation_mode.set(echolesson_generation_mode)

            self.auto_detect_language.set(
                bool(
                    settings.get(
                        "auto_detect_language",
                        DEFAULT_AUTO_DETECT_LANGUAGE,
                    )
                )
            )
            default_language = str(
                settings.get(
                    "default_untagged_language",
                    DEFAULT_UNTAGGED_LANGUAGE,
                )
            ).upper()
            if default_language in {"EN", "ES"}:
                self.default_untagged_language.set(language_name(default_language))
            self.open_audio_when_finished.set(
                bool(settings.get("open_audio_when_finished", False))
            )

            input_folder = settings.get("last_input_folder", "")
            output_folder = settings.get("last_output_folder", "")
            if isinstance(input_folder, str):
                self._last_input_folder = input_folder
            if isinstance(output_folder, str):
                self._last_output_folder = output_folder
            openai_api_key = settings.get("openai_api_key_placeholder", "")
            if isinstance(openai_api_key, str):
                self.openai_api_key_placeholder.set(openai_api_key)
        finally:
            self._is_loading_settings = False
        self._save_settings()

    def _attach_settings_traces(self) -> None:
        """Save settings whenever persistent UI state changes."""

        watched_variables = [
            self.default_output_folder,
            self.theme_preference,
            self.remember_last_selected_mode,
            self.selected_english_voice,
            self.selected_spanish_voice,
            self.selected_speaker_1_voice,
            self.selected_speaker_2_voice,
            self.selected_rate_label,
            self.selected_volume_label,
            self.auto_learning_pauses,
            self.selected_auto_pause_label,
            self.auto_pause_seconds,
            self.selected_auto_pause_segmentation,
            self.selected_conversion_mode,
            self.echolesson_generation_mode,
            self.auto_detect_language,
            self.default_untagged_language,
            self.open_audio_when_finished,
            self.openai_api_key_placeholder,
        ]
        for variable in watched_variables:
            variable.trace_add("write", lambda *_args: self._save_settings())

    def _settings_payload(self) -> dict[str, Any]:
        """Return the configuration values safe to persist."""

        return {
            "default_output_folder": self.default_output_folder.get(),
            "theme_preference": self.theme_preference.get(),
            "remember_last_selected_mode": bool(
                self.remember_last_selected_mode.get()
            ),
            "english_voice": self.selected_english_voice.get(),
            "spanish_voice": self.selected_spanish_voice.get(),
            "speaker_1_voice": self.selected_speaker_1_voice.get(),
            "speaker_2_voice": self.selected_speaker_2_voice.get(),
            "speech_rate": self.selected_rate_label.get(),
            "volume": self.selected_volume_label.get(),
            "conversion_mode": (
                self._conversion_mode_value()
                if self.remember_last_selected_mode.get()
                else DEFAULT_CONVERSION_MODE
            ),
            "echolesson_generation_mode": self.echolesson_generation_mode.get(),
            "auto_learning_pauses": bool(self.auto_learning_pauses.get()),
            "auto_pause_seconds": int(self.auto_pause_seconds.get()),
            "auto_pause_segmentation": self._auto_pause_segmentation_value(),
            "auto_detect_language": bool(self.auto_detect_language.get()),
            "default_untagged_language": self._default_untagged_language_code(),
            "open_audio_when_finished": bool(self.open_audio_when_finished.get()),
            "openai_api_key_placeholder": self.openai_api_key_placeholder.get(),
            "last_input_folder": self._last_input_folder,
            "last_output_folder": self._last_output_folder,
        }

    def _save_settings(self) -> None:
        """Persist settings without interrupting the user on file errors."""

        if self._is_loading_settings:
            return

        try:
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS_FILE.write_text(
                json.dumps(self._settings_payload(), indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _on_close(self) -> None:
        """Save settings before closing the application."""

        self._save_settings()
        if self.custom_cursor is not None:
            self.custom_cursor.destroy()
        self.destroy()

    def _choose_pdf(self) -> None:
        """Ask the user to select a PDF file and show the page count."""

        initial_directory = self._last_input_folder or None
        path = filedialog.askopenfilename(
            title="Select a PDF file",
            initialdir=initial_directory,
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not path:
            return

        self._load_pdf(Path(path))

    def _load_pdf(self, pdf_path: Path) -> None:
        """Load a PDF into the UI from Browse or the clickable PDF area."""

        if pdf_path.suffix.lower() != ".pdf":
            self.pdf_select_area.reset_state()
            messagebox.showerror(
                "Invalid file",
                "That file is not a PDF. Please choose a PDF file.",
            )
            return

        try:
            page_count = self._read_pdf_page_count(pdf_path)
        except Exception as exc:
            self.pdf_select_area.reset_state()
            messagebox.showerror("PDF could not be loaded", str(exc))
        else:
            self.pdf_path.set(str(pdf_path))
            self._last_input_folder = str(pdf_path.parent)
            if not self.output_path.get():
                self._set_default_output_for_pdf(pdf_path)
            self._apply_page_count(page_count)
            self.pdf_select_area.set_selected_file(pdf_path.name)
            self._save_settings()
            if self._conversion_mode_value() == "echolesson":
                self._generate_lesson_structure(silent=True)

    def _set_default_output_for_pdf(self, pdf_path: Path) -> None:
        """Set a new MP3 path using the configured default output folder."""

        output_folder = self.default_output_folder.get().strip()
        if output_folder:
            output_path = Path(output_folder) / f"{pdf_path.stem}.mp3"
        else:
            output_path = pdf_path.with_suffix(".mp3")
        self.output_path.set(str(output_path))
        self._last_output_folder = str(output_path.parent)

    def _choose_output(self) -> None:
        """Ask the user where the MP3 should be saved."""

        initial_file = "audiobook.mp3"
        if self.pdf_path.get():
            initial_file = f"{Path(self.pdf_path.get()).stem}.mp3"
        initial_directory = (
            self.default_output_folder.get().strip()
            or self._last_output_folder
            or None
        )

        path = filedialog.asksaveasfilename(
            title="Save audiobook as",
            defaultextension=".mp3",
            initialfile=initial_file,
            initialdir=initial_directory,
            filetypes=[("MP3 files", "*.mp3"), ("All files", "*.*")],
        )
        if path:
            self.output_path.set(path)
            self._last_output_folder = str(Path(path).parent)
            self._save_settings()

    def _open_last_audio(self) -> None:
        """Open the most recently generated MP3."""

        if self._last_output_path is None:
            return
        try:
            self._open_path(self._last_output_path)
        except PDFAudiobookError as exc:
            messagebox.showerror("Could not open audio", str(exc))

    def _reveal_last_mp3(self) -> None:
        """Reveal the most recently generated MP3 in the file manager."""

        if self._last_output_path is None:
            return
        try:
            self._reveal_path(self._last_output_path)
        except PDFAudiobookError as exc:
            messagebox.showerror("Could not reveal MP3", str(exc))

    @staticmethod
    def _open_path(path: Path) -> None:
        """Open a file or folder with the platform default application."""

        try:
            if platform.system() == "Darwin":
                subprocess.Popen(["open", str(path)])
            elif platform.system() == "Windows":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                opener = shutil.which("xdg-open") or shutil.which("gio")
                if opener is None:
                    raise PDFAudiobookError(
                        "No supported opener was found for this system."
                    )
                command = [opener, str(path)]
                if Path(opener).name == "gio":
                    command = [opener, "open", str(path)]
                subprocess.Popen(command)
        except OSError as exc:
            raise PDFAudiobookError(
                "Your system could not open the selected file or folder."
            ) from exc

    @staticmethod
    def _reveal_path(path: Path) -> None:
        """Reveal a file in the platform file manager."""

        try:
            if platform.system() == "Darwin":
                subprocess.Popen(["open", "-R", str(path)])
            elif platform.system() == "Windows":
                subprocess.Popen(["explorer", "/select,", str(path)])
            else:
                PDFAudiobookApp._open_path(path.parent)
        except OSError as exc:
            raise PDFAudiobookError(
                "Your system could not reveal the selected file."
            ) from exc

    def _update_page_count(self, pdf_path: Path) -> None:
        """Read and display the number of pages in the selected PDF."""

        count = self._read_pdf_page_count(pdf_path)
        self._apply_page_count(count)

    @staticmethod
    def _read_pdf_page_count(pdf_path: Path) -> int:
        """Return the number of pages in a valid PDF."""

        try:
            reader = PdfReader(str(pdf_path))
        except Exception as exc:
            traceback.print_exc()
            raise

        return len(reader.pages)

    def _apply_page_count(self, count: int) -> None:
        """Display loaded PDF page count and ready status."""

        self.page_count.set(f"Pages: {count}")
        self.status_text.set("PDF loaded. Review options, then generate audio.")

    def _start_conversion(self) -> None:
        """Validate user input and start the background conversion worker."""

        if self._is_processing:
            return

        print(
            "START CONVERSION BUTTON: "
            f"selected_ui_mode={self.selected_conversion_mode.get()} "
            f"resolved_mode={self._conversion_mode_value()}"
        )

        try:
            settings = self._get_settings()
        except ValueError as exc:
            messagebox.showerror("Missing information", str(exc))
            return

        self._is_processing = True
        self.convert_button.configure(state=tk.DISABLED)
        self.open_audio_button.configure(state=tk.DISABLED)
        self.reveal_mp3_button.configure(state=tk.DISABLED)
        self._refresh_control_cursors()
        self._last_output_path = None
        self._set_progress(0)
        self.progress_bar.start()
        self.status_text.set("Starting conversion...")

        worker = threading.Thread(
            target=self._run_conversion,
            args=(settings,),
            daemon=True,
        )
        worker.start()

    def _start_voice_preview(self) -> None:
        """Start the background voice preview worker."""

        if self._is_processing:
            return

        print("Preview Voice started")
        settings = self._get_voice_preview_settings()
        self._is_processing = True
        self.convert_button.configure(state=tk.DISABLED)
        if hasattr(self, "preview_button"):
            self.preview_button.configure(state=tk.DISABLED)
        self._refresh_control_cursors()
        self._set_progress(0)
        self.progress_bar.start()
        self.status_text.set("Generating voice preview...")

        worker = threading.Thread(
            target=self._run_voice_preview,
            args=(settings,),
            daemon=True,
        )
        worker.start()

    def _get_settings(self) -> ConversionSettings:
        """Collect validated settings from the UI controls."""

        if not self.pdf_path.get():
            raise ValueError("Please select a PDF file.")
        if not self.output_path.get():
            raise ValueError("Please choose where to save the MP3 file.")

        pdf_path = Path(self.pdf_path.get())
        output_path = Path(self.output_path.get())

        if not pdf_path.exists():
            raise ValueError("The selected PDF file does not exist.")
        if output_path.suffix.lower() != ".mp3":
            output_path = output_path.with_suffix(".mp3")
            self.output_path.set(str(output_path))

        conversion_mode = self._conversion_mode_value()
        lesson_markup = self._lesson_structure_markup()
        if conversion_mode == "echolesson" and not lesson_markup:
            self._generate_lesson_structure(silent=True)
            lesson_markup = self._lesson_structure_markup()
            if not lesson_markup:
                raise ValueError(
                    "EchoLearn could not analyze this PDF for learning audio."
                )
        print(
            "GET SETTINGS: "
            f"conversion_mode={conversion_mode} "
            f"lesson_markup_chars={len(lesson_markup)}"
        )

        return ConversionSettings(
            conversion_mode=conversion_mode,
            lesson_markup=lesson_markup,
            speaker_1_voice_id=self._selected_voice_id(
                self.selected_speaker_1_voice.get(),
                self._all_voice_options(),
                DEFAULT_ENGLISH_VOICE,
            ),
            speaker_2_voice_id=self._selected_voice_id(
                self.selected_speaker_2_voice.get(),
                self._all_voice_options(),
                DEFAULT_SPANISH_VOICE,
            ),
            pdf_path=pdf_path,
            output_path=output_path,
            english_voice_id=self._selected_voice_id(
                self.selected_english_voice.get(),
                self._english_voice_options,
                DEFAULT_ENGLISH_VOICE,
            ),
            spanish_voice_id=self._selected_voice_id(
                self.selected_spanish_voice.get(),
                self._spanish_voice_options,
                DEFAULT_SPANISH_VOICE,
            ),
            rate=int(self.rate.get()),
            volume=int(self.volume.get()),
            auto_detect_language=bool(self.auto_detect_language.get()),
            default_untagged_language=self._default_untagged_language_code(),
            auto_learning_pauses=bool(self.auto_learning_pauses.get()),
            auto_pause_seconds=int(self.auto_pause_seconds.get()),
            auto_pause_segmentation=self._auto_pause_segmentation_value(),
        )

    def _default_untagged_language_code(self) -> str:
        """Return the language code selected for uncertain untagged text."""

        return "ES" if self.default_untagged_language.get() == "Spanish" else "EN"

    def _get_voice_preview_settings(self) -> VoicePreviewSettings:
        """Collect voice preview settings without requiring a PDF."""

        return VoicePreviewSettings(
            english_voice_id=self._selected_voice_id(
                self.selected_english_voice.get(),
                self._english_voice_options,
                DEFAULT_ENGLISH_VOICE,
            ),
            spanish_voice_id=self._selected_voice_id(
                self.selected_spanish_voice.get(),
                self._spanish_voice_options,
                DEFAULT_SPANISH_VOICE,
            ),
            rate=int(self.rate.get()),
            volume=int(self.volume.get()),
        )

    @staticmethod
    def _selected_voice_id(
        selected_label: str,
        options: list[VoiceOption],
        default_voice_id: str,
    ) -> str:
        """Return the selected edge-tts voice id, if one is available."""

        for option in options:
            if option.label == selected_label:
                return option.voice_id
        return selected_label or default_voice_id

    def _all_voice_options(self) -> list[VoiceOption]:
        """Return every voice available for explicit EchoLesson speakers."""

        return [*self._english_voice_options, *self._spanish_voice_options]

    def _update_rate_from_label(self, _event: tk.Event | None = None) -> None:
        """Map the selected speech-rate label to the internal TTS value."""

        self.rate.set(RATE_OPTIONS.get(self.selected_rate_label.get(), DEFAULT_RATE))

    def _update_volume_from_label(self, _event: tk.Event | None = None) -> None:
        """Map the selected volume label to the internal TTS value."""

        self.volume.set(
            VOLUME_OPTIONS.get(self.selected_volume_label.get(), DEFAULT_VOLUME)
        )

    def _update_auto_pause_from_label(self, _event: tk.Event | None = None) -> None:
        """Map the selected auto-pause label to seconds."""

        self.auto_pause_seconds.set(
            AUTO_PAUSE_OPTIONS.get(
                self.selected_auto_pause_label.get(),
                DEFAULT_AUTO_PAUSE_SECONDS,
            )
        )

    @staticmethod
    def _auto_pause_label_for_seconds(seconds: int) -> str:
        """Return the dropdown label for an auto-pause duration."""

        for label, value in AUTO_PAUSE_OPTIONS.items():
            if value == seconds:
                return label
        return "3 seconds"

    def _auto_pause_segmentation_value(self) -> str:
        """Return the internal auto-pause segmentation mode."""

        return AUTO_PAUSE_SEGMENTATION_OPTIONS.get(
            self.selected_auto_pause_segmentation.get(),
            DEFAULT_AUTO_PAUSE_SEGMENTATION,
        )

    @staticmethod
    def _auto_pause_segmentation_label_for_value(value: str) -> str:
        """Return the dropdown label for an auto-pause segmentation value."""

        for label, option_value in AUTO_PAUSE_SEGMENTATION_OPTIONS.items():
            if option_value == value:
                return label
        return "Paragraph"

    def _conversion_mode_value(self) -> str:
        """Return the internal conversion mode selected in the UI."""

        return CONVERSION_MODE_OPTIONS.get(
            self.selected_conversion_mode.get(),
            DEFAULT_CONVERSION_MODE,
        )

    @staticmethod
    def _conversion_mode_label_for_value(value: str) -> str:
        """Return the display label for a stored conversion mode."""

        for label, option_value in CONVERSION_MODE_OPTIONS.items():
            if option_value == value:
                return label
        return "Audiobook"

    def _update_conversion_mode_description(self) -> None:
        """Refresh the mode-specific guidance shown in the UI."""

        if self._conversion_mode_value() == "echolesson":
            self.conversion_mode_description.set(ECHOLESSON_MODE_DESCRIPTION)
            self.convert_button.configure(text="Generate Learning Audio")
        else:
            self.conversion_mode_description.set(AUDIOBOOK_MODE_DESCRIPTION)
            self.convert_button.configure(text="Generate Audio")
        self._refresh_mode_cards()
        self._sync_lesson_builder_visibility()
        if self._conversion_mode_value() == "echolesson" and self.pdf_path.get():
            self._generate_lesson_structure(silent=True)

    def _sync_lesson_builder_visibility(self) -> None:
        """Show only the controls relevant to the selected experience."""

        if self._conversion_mode_value() == "echolesson":
            self._sync_content_summary_visibility()
        else:
            self.content_summary_card.grid_remove()

    def _sync_content_summary_visibility(self) -> None:
        """Show the compact content summary only when it has useful content."""

        if (
            self._conversion_mode_value() == "echolesson"
            and bool(self._lesson_structure_markup())
        ):
            self.content_summary_card.grid()
        else:
            self.content_summary_card.grid_remove()

    def _generate_lesson_structure(self, *, silent: bool = False) -> bool:
        """Generate deterministic EchoLearn Markup from the selected PDF."""

        if not self.pdf_path.get():
            if not silent:
                messagebox.showerror(
                    "Missing PDF",
                    "Please select a PDF before generating lesson structure.",
                )
            return False

        pdf_path = Path(self.pdf_path.get())
        if not pdf_path.exists():
            if not silent:
                messagebox.showerror(
                    "Missing PDF",
                    "The selected PDF file does not exist.",
                )
            return False

        try:
            pdf_text = extract_text_from_pdf(pdf_path, lambda _page, _total: None)
            lesson_builder = LessonBuilder()
            generated_structure, lesson_analysis = (
                lesson_builder.generate_structure_with_analysis(pdf_text)
            )
        except PDFAudiobookError as exc:
            if not silent:
                messagebox.showerror("Could not generate lesson structure", str(exc))
            return False
        except Exception as exc:
            traceback.print_exc()
            if not silent:
                messagebox.showerror(
                    "Could not generate lesson structure",
                    "EchoLearn could not generate a lesson structure from this PDF.",
                )
            return False

        if not generated_structure:
            if not silent:
                messagebox.showerror(
                    "Could not generate lesson structure",
                    "No usable text was found for lesson structure generation.",
                )
            return False

        self._set_lesson_structure_preview(generated_structure)
        print(lesson_analysis.format())
        self.status_text.set("Content analyzed. Ready to generate learning audio.")
        return True

    def _set_lesson_structure_preview(self, markup: str) -> None:
        """Replace the editable lesson structure preview text."""

        self.lesson_structure_preview.configure(state=tk.NORMAL)
        self.lesson_structure_preview.delete("1.0", tk.END)
        self.lesson_structure_preview.insert("1.0", markup)
        self._update_lesson_preview_insights()

    def _lesson_structure_markup(self) -> str:
        """Return the edited EchoLesson markup from Generated Structure."""

        return self.lesson_structure_preview.get("1.0", tk.END).strip()

    def _lesson_structure_markup_b(self) -> str:
        """Return the edited EchoLesson markup from Editable Structure."""

        return self.lesson_structure_preview_b.get("1.0", tk.END).strip()

    def _duplicate_lesson_structure(self) -> None:
        """Copy Generated Structure into Editable Structure."""

        markup = self._lesson_structure_markup()
        self.lesson_structure_preview_b.configure(state=tk.NORMAL)
        self.lesson_structure_preview_b.delete("1.0", tk.END)
        self.lesson_structure_preview_b.insert("1.0", markup)
        self._update_lesson_comparison_summary()
        self.status_text.set(
            "Generated Structure copied to Editable Structure."
        )

    def _copy_lesson_structure(self) -> None:
        """Copy generated lesson markup from Generated Structure."""

        markup = self._lesson_structure_markup()
        if not markup:
            return
        self.clipboard_clear()
        self.clipboard_append(markup)
        self.status_text.set("Lesson structure copied to clipboard.")

    def _update_lesson_comparison_summary(self) -> None:
        """Refresh the generated/editable structure comparison."""

        self.lesson_comparison_summary.set(
            self._format_lesson_comparison_summary(
                self._lesson_structure_markup(),
                self._lesson_structure_markup_b(),
            )
        )

    def _update_lesson_analysis_dashboard(self) -> None:
        """Refresh the generated structure lesson analysis dashboard."""

        markup = self._lesson_structure_markup()
        if not markup:
            self.lesson_analysis_dashboard.set(
                "Choose a PDF in EchoLesson Mode to see a content summary."
            )
            self._sync_content_summary_visibility()
            return

        analysis = analyze_lesson_structure(markup)
        self.lesson_analysis_dashboard.set(self._format_content_summary(analysis))
        self._sync_content_summary_visibility()

    def _update_lesson_preview_insights(self) -> None:
        """Refresh lesson analysis and comparison summaries."""

        self._update_lesson_analysis_dashboard()
        self._update_lesson_comparison_summary()

    @staticmethod
    def _format_content_summary(analysis: Any) -> str:
        """Return a friendly content summary with no internal markup."""

        detected: list[str] = []
        if analysis.dialogue_count:
            detected.append("✓ Dialogue")
        if analysis.practice_count:
            detected.append("✓ Practice")
        if analysis.review_count:
            detected.append("✓ Review")
        if analysis.explanation_count:
            detected.append("✓ Explanation")
        if not detected:
            detected.append("No learning patterns detected yet")

        return (
            "Title:\n"
            f"{analysis.title}\n\n"
            "Detected:\n"
            + "\n".join(detected)
            + "\n\n"
            "Estimated Length:\n"
            f"{analysis.estimated_audio_length}\n\n"
            "Learning Quality:\n"
            f"{analysis.learning_quality}\n\n"
            "Suggestions:\n"
            + "\n".join(analysis.suggestions)
        )

    @staticmethod
    def _format_lesson_comparison_summary(
        preview_a_markup: str,
        preview_b_markup: str,
    ) -> str:
        """Return compact counts for both lesson previews."""

        preview_a_counts = PDFAudiobookApp._count_lesson_markup_parts(
            preview_a_markup
        )
        preview_b_counts = PDFAudiobookApp._count_lesson_markup_parts(
            preview_b_markup
        )
        return (
            "Generated Structure:\n"
            f"- Dialogues: {preview_a_counts['dialogues']}\n"
            f"- Practice Questions: {preview_a_counts['practice']}\n"
            f"- Review Sections: {preview_a_counts['review']}\n\n"
            "Editable Structure:\n"
            f"- Dialogues: {preview_b_counts['dialogues']}\n"
            f"- Practice Questions: {preview_b_counts['practice']}\n"
            f"- Review Sections: {preview_b_counts['review']}"
        )

    @staticmethod
    def _count_lesson_markup_parts(markup: str) -> dict[str, int]:
        """Count key EchoLesson sections in editable markup."""

        counts = {
            "dialogues": 0,
            "practice": 0,
            "review": 0,
        }
        current_section = ""
        previous_section = ""

        for raw_line in markup.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            tag_match = ECHOLESSON_TAG_PATTERN.match(line)
            if tag_match:
                tag = tag_match.group(1).upper()
                if tag in {
                    "TITLE",
                    "FLOW",
                    "EXPLANATION",
                    "DIALOG",
                    "PRACTICE",
                    "REVIEW",
                }:
                    current_section = tag
                    if tag == "DIALOG" and previous_section != "DIALOG":
                        counts["dialogues"] += 1
                    if tag == "REVIEW" and previous_section != "REVIEW":
                        counts["review"] += 1
                    previous_section = tag
                continue

            if current_section == "PRACTICE":
                counts["practice"] += 1

        return counts

    def _set_progress(self, percent: float) -> None:
        """Update progress value and percentage label together."""

        bounded_percent = max(0.0, min(percent, 100.0))
        self.progress_value.set(bounded_percent)
        self.progress_percent.set(f"{bounded_percent:.0f}%")

    def _run_conversion(self, settings: ConversionSettings) -> None:
        """Worker-thread conversion body."""

        try:
            log_runtime_paths(settings.output_path)
            print(f"RUN CONVERSION MODE: {settings.conversion_mode}")
            if settings.conversion_mode == "echolesson":
                print(
                    "ECHOLESSON SOURCE: editable preview "
                    f"chars={len(settings.lesson_markup)}"
                )
                self._messages.put(
                    ProgressMessage("status", "Preparing edited lesson markup...")
                )
            else:
                print(f"AUDIOBOOK SOURCE: PDF {settings.pdf_path}")
                self._messages.put(ProgressMessage("status", "Processing PDF..."))

            def progress_callback(page: int, total: int) -> None:
                percent = (page / total) * 70
                self._messages.put(ProgressMessage("progress", percent))
                self._messages.put(
                    ProgressMessage("status", f"Processing page {page} of {total}")
                )

            smart_cleanup_records: list[SmartCleanupRecord] = []
            if settings.conversion_mode == "echolesson":
                text = settings.lesson_markup
                self._messages.put(ProgressMessage("progress", 70))
            else:
                text = extract_text_from_pdf(settings.pdf_path, progress_callback)
            if DEBUG_MODE:
                try:
                    write_debug_text(text, DEBUG_NORMALIZED_TEXT_FILE)
                except OSError:
                    traceback.print_exc()
            if settings.conversion_mode != "echolesson":
                text, smart_cleanup_records = smart_pdf_cleanup(text)

            auto_pause_debug_insertions: list[int] = []
            if settings.conversion_mode == "echolesson":
                print("EchoLesson markup parser: ON")
                print(
                    "ECHOLESSON SPEAKER VOICES: "
                    f"speaker_1={settings.speaker_1_voice_id} "
                    f"speaker_2={settings.speaker_2_voice_id}"
                )
                segments, warnings = parse_echolesson_markup(
                    text,
                    speaker_1_voice_id=settings.speaker_1_voice_id,
                    speaker_2_voice_id=settings.speaker_2_voice_id,
                    practice_pause_seconds=settings.auto_pause_seconds,
                )
                print(f"ECHOLESSON PARSER RECEIVED CHARS: {len(text)}")
                log_echolesson_segments(segments)
                final_segments_before_auto_pauses = segments
            else:
                print(
                    "Auto-detect language: "
                    f"{'ON' if settings.auto_detect_language else 'OFF'}"
                )
                print(
                    "Default language for untagged text: "
                    f"{settings.default_untagged_language}"
                )
                segments, warnings = parse_audio_script(
                    text,
                    auto_detect_language=settings.auto_detect_language,
                    default_language=settings.default_untagged_language,
                    auto_learning_pauses_enabled=settings.auto_learning_pauses,
                    auto_pause_segmentation=settings.auto_pause_segmentation,
                )
                print(
                    "Auto Learning Pauses: "
                    f"{'ON' if settings.auto_learning_pauses else 'OFF'}"
                )
                final_segments_before_auto_pauses = segments
                if settings.auto_learning_pauses:
                    auto_pause_debug_insertions = auto_pause_inserted_after_text_segments(
                        final_segments_before_auto_pauses
                    )
                    segments = add_auto_learning_pauses(
                        final_segments_before_auto_pauses,
                        auto_pause_seconds=settings.auto_pause_seconds,
                    )
            if DEBUG_MODE:
                try:
                    if settings.conversion_mode != "echolesson":
                        write_smart_cleanup_debug(
                            smart_cleanup_records,
                            final_segments_before_auto_pauses,
                            auto_pause_debug_insertions,
                            SMART_CLEANUP_DEBUG_FILE,
                        )
                    write_debug_segments(segments, DEBUG_SEGMENTS_FILE)
                except OSError:
                    traceback.print_exc()

            self._messages.put(
                ProgressMessage(
                    "status",
                    (
                        "Creating learning audio MP3..."
                        if settings.conversion_mode == "echolesson"
                        else "Creating full audiobook MP3..."
                    ),
                )
            )
            self._messages.put(ProgressMessage("progress", 72))

            service = TextToSpeechService()
            service.save_segments_to_mp3(
                segments,
                settings.output_path,
                english_voice_id=settings.english_voice_id,
                spanish_voice_id=settings.spanish_voice_id,
                rate=settings.rate,
                volume=settings.volume,
                progress_callback=lambda current, total: (
                    self._messages.put(
                        ProgressMessage("progress", 70 + (current / total) * 28)
                    ),
                    self._messages.put(
                        ProgressMessage(
                            "status",
                            f"Generating segment {current} of {total}",
                        )
                    ),
                ),
            )

            self._messages.put(ProgressMessage("progress", 100))
            self._messages.put(
                ProgressMessage(
                    "success",
                    ConversionResult(settings.output_path, warnings),
                )
            )
        except PDFAudiobookError as exc:
            self._messages.put(ProgressMessage("error", str(exc)))
        except PermissionError:
            self._messages.put(
                ProgressMessage(
                    "error",
                    "The MP3 could not be saved. Check that the destination folder is writable.",
                )
            )
        except Exception as exc:
            traceback.print_exc()
            self._messages.put(ProgressMessage("error", f"Unexpected error: {exc!r}"))
            raise

    def _run_voice_preview(self, settings: VoicePreviewSettings) -> None:
        """Worker-thread voice preview body."""

        preview_path: Path | None = None
        try:
            fd, path = tempfile.mkstemp(
                prefix="echolearn-preview-",
                suffix=".mp3",
                dir=tempfile.gettempdir(),
            )
            os.close(fd)
            preview_path = Path(path)

            print("Generating preview audio")
            self._messages.put(ProgressMessage("status", "Generating preview audio..."))
            self._messages.put(ProgressMessage("progress", 30))

            service = TextToSpeechService()
            service.save_preview_to_mp3(
                preview_path,
                english_voice_id=settings.english_voice_id,
                spanish_voice_id=settings.spanish_voice_id,
                rate=settings.rate,
                volume=settings.volume,
            )

            print("Playing preview audio")
            self._messages.put(ProgressMessage("status", "Playing preview audio..."))
            self._messages.put(ProgressMessage("progress", 75))
            play_audio_file(preview_path)

            print("Preview completed")
            self._messages.put(ProgressMessage("progress", 100))
            self._messages.put(ProgressMessage("preview_success"))
        except PDFAudiobookError as exc:
            self._messages.put(ProgressMessage("preview_error", str(exc)))
        except Exception as exc:
            traceback.print_exc()
            self._messages.put(
                ProgressMessage("preview_error", f"Unexpected preview error: {exc!r}")
            )
        finally:
            if preview_path is not None:
                try:
                    preview_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def _process_worker_messages(self) -> None:
        """Apply worker-thread messages safely on the Tkinter UI thread."""

        try:
            while True:
                message = self._messages.get_nowait()
                if message.kind == "progress":
                    self._set_progress(float(message.payload))
                elif message.kind == "status":
                    self.status_text.set(str(message.payload))
                elif message.kind == "success":
                    self._finish_processing()
                    result = message.payload
                    path = Path(result.output_path)
                    self._last_output_path = path
                    self.open_audio_button.configure(state=tk.NORMAL)
                    self.reveal_mp3_button.configure(state=tk.NORMAL)
                    self._refresh_control_cursors()
                    self.status_text.set(f"Done: {path}")
                    warning_text = ""
                    if result.warnings:
                        warning_text = "\n\nWarnings:\n" + "\n".join(result.warnings)
                    messagebox.showinfo(
                        "Audiobook created",
                        (
                            "Your audiobook was saved successfully:\n\n"
                            f"{path}\n\nUse Open Audio to listen now, or Reveal MP3 "
                            f"to show the file in Finder.{warning_text}"
                        ),
                    )
                    if self.open_audio_when_finished.get():
                        self._open_last_audio()
                elif message.kind == "error":
                    self._finish_processing()
                    self.status_text.set("Conversion failed.")
                    messagebox.showerror("Conversion failed", str(message.payload))
                elif message.kind == "preview_success":
                    self._finish_processing()
                    self.status_text.set("Voice preview completed.")
                elif message.kind == "preview_error":
                    self._finish_processing()
                    self.status_text.set("Voice preview failed.")
                    messagebox.showerror("Voice preview failed", str(message.payload))
        except queue.Empty:
            pass
        finally:
            self.after(100, self._process_worker_messages)

    def _finish_processing(self) -> None:
        """Restore controls after processing finishes."""

        self._is_processing = False
        self.progress_bar.stop()
        self.pdf_select_area.reset_state()
        self.convert_button.configure(state=tk.NORMAL)
        if hasattr(self, "preview_button"):
            self.preview_button.configure(state=tk.NORMAL)
        self._refresh_control_cursors()


def main() -> None:
    """Application entry point."""

    ensure_app_directories()
    log_runtime_paths()
    app = PDFAudiobookApp()

    def show_main_window() -> None:
        app.deiconify()
        app.lift()
        app.focus_force()

    SplashScreen(app, on_complete=show_main_window)
    app.mainloop()


if __name__ == "__main__":
    main()
