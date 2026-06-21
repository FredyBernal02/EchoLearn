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

from lesson_builder import LessonBuilder

APP_TITLE = "EchoLearn"
LOGO_FILE = "echolearn_logo.png"
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
CONVERSION_MODE_OPTIONS = {
    "Audiobook": "audiobook",
    "EchoLesson": "echolesson",
}
AUDIOBOOK_MODE_DESCRIPTION = (
    "Continuous listening audio using current language detection and voices. "
    "Minimal interruptions; Auto Learning Pauses are off by default."
)
ECHOLESSON_MODE_DESCRIPTION = (
    "EchoLesson Mode turns PDFs into editable deterministic lesson structures "
    "before learning audio generation."
)
LESSON_STRUCTURE_PLACEHOLDER = """[TITLE]
Lesson Title

[FLOW]
Introduction text...

[DIALOG]
[SPEAKER_1]
Hello.

[SPEAKER_2]
Hi.

[PRACTICE]
Repeat this sentence.
"""
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
SETTINGS_FILE = APP_DATA_DIR / "echolearn_settings.json"
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
            fg="#eef2f8",
            font=("TkDefaultFont", 11),
        )
        self.label.grid(row=0, column=1, sticky="w", padx=(12, 0))

        self.canvas.bind("<Button-1>", self._toggle)
        self.label.bind("<Button-1>", self._toggle)
        self.variable.trace_add("write", lambda *_args: self._draw())
        self._draw()

    def _toggle(self, _event: tk.Event) -> None:
        self.variable.set(not self.variable.get())

    def _draw(self) -> None:
        self.canvas.delete("all")
        enabled = self.variable.get()
        fill = "#1db954" if enabled else "#303644"
        knob_x = 28 if enabled else 4
        self.canvas.create_oval(2, 2, 50, 26, fill=fill, outline=fill)
        self.canvas.create_oval(knob_x, 4, knob_x + 20, 24, fill="#ffffff", outline="")


class AnimatedProgressBar(tk.Canvas):
    """Dark themed progress bar with a moving highlight while active."""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        variable: tk.DoubleVar,
        background: str = "#242833",
        accent: str = "#1db954",
    ) -> None:
        super().__init__(
            parent,
            height=16,
            bg="#191c24",
            highlightthickness=0,
            bd=0,
        )
        self.variable = variable
        self.track_color = background
        self.accent_color = accent
        self.highlight_color = "#64f58f"
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

        self.create_rectangle(0, 0, fill_width, height, fill=self.accent_color, outline="")
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
            height=82,
            bg="#191c24",
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.browse_callback = browse_callback
        self._selected_filename = ""
        self.bind("<Configure>", lambda _event: self._draw())
        self.bind("<Button-1>", lambda _event: self.browse_callback())
        self._draw()

    def set_selected_file(self, filename: str) -> None:
        """Show only the current selected PDF name after loading."""

        self._selected_filename = filename
        self._draw()

    def reset_state(self) -> None:
        """Redraw the current selection state."""

        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        width = max(self.winfo_width(), 1)
        height = max(self.winfo_height(), 1)
        border = "#3b4251"
        fill = "#10131a"
        title = "Click to choose PDF"
        subtitle = "Browse from your computer"
        if self._selected_filename:
            title = self._selected_filename
            subtitle = ""

        self.create_rectangle(
            2,
            2,
            width - 2,
            height - 2,
            fill=fill,
            outline=border,
            width=2,
            dash=(8, 5),
        )
        self.create_text(
            width / 2,
            height / 2 - 12,
            text=title,
            fill="#eef2f8",
            font=("TkDefaultFont", 15, "bold"),
        )
        if subtitle:
            self.create_text(
                width / 2,
                height / 2 + 14,
                text=subtitle,
                fill="#9aa4b2",
                font=("TkDefaultFont", 10),
            )


class SplashScreen(tk.Toplevel):
    """Short startup splash screen shown before the main window."""

    def __init__(self, parent: tk.Tk, *, on_complete: Callable[[], None]) -> None:
        super().__init__(parent)
        self.on_complete = on_complete
        self.logo_image: ImageTk.PhotoImage | None = self._load_logo_image()

        self.overrideredirect(True)
        self.configure(bg="#0f1117")
        try:
            self.attributes("-alpha", 0.98)
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
            bg="#0f1117",
            highlightthickness=0,
            bd=0,
        )
        panel.pack(fill=tk.BOTH, expand=True)
        self._draw_panel(panel, width, height)

        content = tk.Frame(panel, bg="#171a22")
        panel.create_window(width / 2, height / 2, window=content)

        if self.logo_image is not None:
            tk.Label(content, image=self.logo_image, bg="#171a22").pack(
                pady=(0, 14)
            )

        tk.Label(
            content,
            text=APP_TITLE,
            bg="#171a22",
            fg="#ffffff",
            font=("TkDefaultFont", 26, "bold"),
        ).pack()
        tk.Label(
            content,
            text="Learn by Listening",
            bg="#171a22",
            fg="#b8c0cc",
            font=("TkDefaultFont", 13),
        ).pack(pady=(4, 16))
        tk.Label(
            content,
            text="Loading your audio workspace...",
            bg="#171a22",
            fg="#76d996",
            font=("TkDefaultFont", 10),
        ).pack()

        self.lift()
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
            fill="#171a22",
            outline="#2e3442",
            width=1,
        )

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
        self.geometry("940x680")
        self.minsize(720, 520)

        self.pdf_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.page_count = tk.StringVar(value="Pages: 0")
        self.status_text = tk.StringVar(value="Choose a PDF to begin.")
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
        self.conversion_mode_description = tk.StringVar(
            value=AUDIOBOOK_MODE_DESCRIPTION
        )
        self.lesson_comparison_summary = tk.StringVar(
            value=self._format_lesson_comparison_summary("", "")
        )
        self.auto_detect_language = tk.BooleanVar(value=DEFAULT_AUTO_DETECT_LANGUAGE)
        self.default_untagged_language = tk.StringVar(
            value=language_name(DEFAULT_UNTAGGED_LANGUAGE)
        )
        self.open_audio_when_finished = tk.BooleanVar(value=False)
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

        self._configure_style()
        self._build_ui()
        self._load_voices()
        self._load_settings()
        self._attach_settings_traces()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._process_worker_messages)

    def _configure_style(self) -> None:
        """Apply a polished dark desktop theme."""

        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        self.configure(bg="#0f1117")

        style.configure("App.TFrame", background="#0f1117")
        style.configure("App.TLabel", background="#0f1117")
        style.configure("Card.TFrame", background="#191c24")
        style.configure(
            "TLabel",
            background="#191c24",
            foreground="#eef2f8",
            padding=(0, 3),
            font=("TkDefaultFont", 11),
        )
        style.configure(
            "Muted.TLabel",
            background="#191c24",
            foreground="#9aa4b2",
            font=("TkDefaultFont", 10),
        )
        style.configure(
            "Title.TLabel",
            background="#0f1117",
            foreground="#ffffff",
            font=("TkDefaultFont", 28, "bold"),
            padding=(0, 0),
        )
        style.configure(
            "Subtitle.TLabel",
            background="#0f1117",
            foreground="#9aa4b2",
            font=("TkDefaultFont", 13),
            padding=(0, 0),
        )
        style.configure(
            "Section.TLabel",
            background="#191c24",
            foreground="#ffffff",
            font=("TkDefaultFont", 16, "bold"),
            padding=(0, 0),
        )
        style.configure(
            "Status.TLabel",
            background="#0f1117",
            foreground="#86efac",
            font=("TkDefaultFont", 10),
        )
        style.configure(
            "TButton",
            background="#2a2f3a",
            foreground="#ffffff",
            borderwidth=0,
            focusthickness=0,
            padding=(14, 8),
            font=("TkDefaultFont", 11, "bold"),
        )
        style.map(
            "TButton",
            background=[("disabled", "#242833"), ("active", "#3a4150")],
            foreground=[("disabled", "#6f7785"), ("active", "#ffffff")],
        )
        style.configure(
            "Primary.TButton",
            background="#1db954",
            foreground="#07110a",
            padding=(20, 11),
            font=("TkDefaultFont", 12, "bold"),
        )
        style.map(
            "Primary.TButton",
            background=[("disabled", "#244431"), ("active", "#28d263")],
            foreground=[("disabled", "#7b9083"), ("active", "#07110a")],
        )
        style.configure(
            "TEntry",
            fieldbackground="#10131a",
            foreground="#eef2f8",
            insertcolor="#eef2f8",
            bordercolor="#303644",
            lightcolor="#303644",
            darkcolor="#303644",
            padding=(10, 8),
        )
        style.configure(
            "TCombobox",
            fieldbackground="#10131a",
            background="#10131a",
            foreground="#eef2f8",
            bordercolor="#303644",
            arrowcolor="#eef2f8",
            padding=(8, 7),
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", "#10131a")],
            foreground=[("readonly", "#eef2f8")],
            selectbackground=[("readonly", "#10131a")],
            selectforeground=[("readonly", "#eef2f8")],
        )
        style.configure(
            "TRadiobutton",
            background="#191c24",
            foreground="#eef2f8",
            padding=(0, 4),
            font=("TkDefaultFont", 11),
        )
        style.map(
            "TRadiobutton",
            background=[("active", "#191c24")],
            foreground=[("active", "#ffffff")],
        )
        style.configure(
            "Horizontal.TProgressbar",
            background="#1db954",
            troughcolor="#242833",
            bordercolor="#242833",
            lightcolor="#1db954",
            darkcolor="#1db954",
            thickness=12,
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

        container = ttk.Frame(self, padding=(20, 18), style="App.TFrame")
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)

        header = ttk.Frame(container, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.columnconfigure(1, weight=1)

        self.logo_image = self._load_logo_image()
        if self.logo_image is not None:
            self.iconphoto(True, self.logo_image)
            ttk.Label(
                header,
                image=self.logo_image,
                style="App.TLabel",
            ).grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 12))

        ttk.Label(header, text=APP_TITLE, style="Title.TLabel").grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(header, text="Learn by Listening", style="Subtitle.TLabel").grid(
            row=1, column=1, sticky="w", pady=(5, 0)
        )

        scroll_area = ttk.Frame(container, style="App.TFrame")
        scroll_area.grid(row=1, column=0, sticky="nsew")
        scroll_area.columnconfigure(0, weight=1)
        scroll_area.rowconfigure(0, weight=1)

        self.content_canvas = tk.Canvas(
            scroll_area,
            bg="#0f1117",
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
        content.columnconfigure(1, weight=1)
        content.rowconfigure(1, weight=1)

        self.pdf_card = self._create_card(content)
        self.pdf_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 12))
        self.pdf_card.columnconfigure(0, weight=1)
        self.pdf_card.columnconfigure(1, weight=1)
        self._add_card_header(self.pdf_card, "PDF", "Source script", "pdf")

        self.pdf_select_area = PDFSelectArea(
            self.pdf_card,
            browse_callback=self._choose_pdf,
        )
        self.pdf_select_area.grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(14, 10)
        )
        ttk.Entry(self.pdf_card, textvariable=self.pdf_path).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(0, 10)
        )
        ttk.Button(self.pdf_card, text="Browse PDF", command=self._choose_pdf).grid(
            row=3, column=0, sticky="w"
        )
        ttk.Label(self.pdf_card, textvariable=self.page_count, style="Muted.TLabel").grid(
            row=3, column=1, sticky="e"
        )

        self.voices_card = self._create_card(content)
        self.voices_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(0, 12))
        self.voices_card.columnconfigure(1, weight=1)
        self._add_card_header(self.voices_card, "Voices", "Bilingual narration", "voices")

        ttk.Label(self.voices_card, text="English voice").grid(
            row=1, column=0, sticky="w", pady=(14, 0)
        )
        self.english_voice_menu = ttk.Combobox(
            self.voices_card,
            textvariable=self.selected_english_voice,
            state="readonly",
            values=[],
        )
        self.english_voice_menu.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=(14, 0))

        ttk.Label(self.voices_card, text="Spanish voice").grid(
            row=2, column=0, sticky="w", pady=(12, 0)
        )
        self.spanish_voice_menu = ttk.Combobox(
            self.voices_card,
            textvariable=self.selected_spanish_voice,
            state="readonly",
            values=[],
        )
        self.spanish_voice_menu.grid(
            row=2, column=1, sticky="ew", padx=(12, 0), pady=(12, 0)
        )

        self.preview_button = ttk.Button(
            self.voices_card,
            text="Preview Voice",
            command=self._start_voice_preview,
        )
        self.preview_button.grid(
            row=3, column=1, sticky="w", padx=(12, 0), pady=(14, 0)
        )

        ToggleSwitch(
            self.voices_card,
            text="Auto-detect language",
            variable=self.auto_detect_language,
            background="#191c24",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(14, 0))

        ttk.Label(self.voices_card, text="Default language for untagged text").grid(
            row=5, column=0, sticky="w", pady=(12, 0)
        )
        self.default_language_menu = ttk.Combobox(
            self.voices_card,
            textvariable=self.default_untagged_language,
            state="readonly",
            values=["English", "Spanish"],
        )
        self.default_language_menu.grid(
            row=5, column=1, sticky="ew", padx=(12, 0), pady=(12, 0)
        )

        self.learning_card = self._create_card(content)
        self.learning_card.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self.learning_card.columnconfigure(1, weight=1)
        self._add_card_header(
            self.learning_card,
            "Learning Modes",
            "Practice patterns",
            "learning",
        )

        ttk.Label(self.learning_card, text="Speech rate").grid(
            row=1, column=0, sticky="w", pady=(14, 0)
        )
        self.rate_menu = ttk.Combobox(
            self.learning_card,
            textvariable=self.selected_rate_label,
            state="readonly",
            values=list(RATE_OPTIONS),
        )
        self.rate_menu.grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=(12, 0), pady=(14, 0)
        )
        self.rate_menu.bind("<<ComboboxSelected>>", self._update_rate_from_label)

        ttk.Label(self.learning_card, text="Volume").grid(
            row=2, column=0, sticky="w", pady=(12, 0)
        )
        self.volume_menu = ttk.Combobox(
            self.learning_card,
            textvariable=self.selected_volume_label,
            state="readonly",
            values=list(VOLUME_OPTIONS),
        )
        self.volume_menu.grid(
            row=2, column=1, columnspan=2, sticky="ew", padx=(12, 0), pady=(12, 0)
        )
        self.volume_menu.bind("<<ComboboxSelected>>", self._update_volume_from_label)

        ToggleSwitch(
            self.learning_card,
            text="Auto Learning Pauses",
            variable=self.auto_learning_pauses,
            background="#191c24",
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(14, 0))

        ttk.Label(self.learning_card, text="Auto pause duration").grid(
            row=4, column=0, sticky="w", pady=(10, 0)
        )
        self.auto_pause_menu = ttk.Combobox(
            self.learning_card,
            textvariable=self.selected_auto_pause_label,
            state="readonly",
            values=list(AUTO_PAUSE_OPTIONS),
            width=10,
        )
        self.auto_pause_menu.grid(
            row=4, column=1, sticky="w", padx=(12, 0), pady=(10, 0)
        )
        self.auto_pause_menu.bind(
            "<<ComboboxSelected>>",
            self._update_auto_pause_from_label,
        )

        ttk.Label(self.learning_card, text="Auto pause by").grid(
            row=5, column=0, sticky="w", pady=(10, 0)
        )
        self.auto_pause_segmentation_menu = ttk.Combobox(
            self.learning_card,
            textvariable=self.selected_auto_pause_segmentation,
            state="readonly",
            values=list(AUTO_PAUSE_SEGMENTATION_OPTIONS),
            width=12,
        )
        self.auto_pause_segmentation_menu.grid(
            row=5, column=1, sticky="w", padx=(12, 0), pady=(10, 0)
        )

        self.mode_card = self._create_card(content)
        self.mode_card.grid(row=2, column=0, sticky="nsew", padx=(0, 8))
        self.mode_card.columnconfigure(0, weight=1)
        self._add_card_header(
            self.mode_card,
            "Conversion Mode",
            "Choose the listening experience",
            "mode",
        )

        ttk.Radiobutton(
            self.mode_card,
            text="Audiobook",
            variable=self.selected_conversion_mode,
            value="Audiobook",
            command=self._update_conversion_mode_description,
        ).grid(row=1, column=0, sticky="w", pady=(14, 0))
        ttk.Label(
            self.mode_card,
            text="Convert documents into continuous listening audio.",
            style="Muted.TLabel",
            wraplength=360,
        ).grid(row=2, column=0, sticky="w", pady=(2, 0))

        ttk.Radiobutton(
            self.mode_card,
            text="EchoLesson",
            variable=self.selected_conversion_mode,
            value="EchoLesson",
            command=self._update_conversion_mode_description,
        ).grid(row=3, column=0, sticky="w", pady=(14, 0))
        ttk.Label(
            self.mode_card,
            text="Convert educational content into structured learning audio.",
            style="Muted.TLabel",
            wraplength=360,
        ).grid(row=4, column=0, sticky="w", pady=(2, 0))
        ttk.Label(
            self.mode_card,
            textvariable=self.conversion_mode_description,
            style="Muted.TLabel",
            wraplength=360,
        ).grid(row=5, column=0, sticky="w", pady=(14, 0))

        self.lesson_builder_card = self._create_card(content)
        self.lesson_builder_card.grid(row=3, column=0, sticky="nsew", padx=(0, 8))
        self.lesson_builder_card.columnconfigure(0, weight=1)
        self.lesson_builder_card.columnconfigure(1, weight=1)
        self._add_card_header(
            self.lesson_builder_card,
            "EchoLesson Builder",
            "Future AI-powered lesson generation",
            "builder",
        )

        ttk.Label(
            self.lesson_builder_card,
            text=(
                "Future AI-powered lesson generation. This area will display "
                "structured EchoLearn content before audio conversion."
            ),
            style="Muted.TLabel",
            wraplength=360,
        ).grid(row=1, column=0, sticky="w", pady=(14, 0))
        ttk.Label(
            self.lesson_builder_card,
            text="Speaker 1 Voice",
        ).grid(row=2, column=0, sticky="w", pady=(14, 0))
        self.speaker_1_voice_menu = ttk.Combobox(
            self.lesson_builder_card,
            textvariable=self.selected_speaker_1_voice,
            state="readonly",
            values=[],
        )
        self.speaker_1_voice_menu.grid(
            row=2, column=1, sticky="ew", padx=(12, 0), pady=(14, 0)
        )

        ttk.Label(
            self.lesson_builder_card,
            text="Speaker 2 Voice",
        ).grid(row=3, column=0, sticky="w", pady=(12, 0))
        self.speaker_2_voice_menu = ttk.Combobox(
            self.lesson_builder_card,
            textvariable=self.selected_speaker_2_voice,
            state="readonly",
            values=[],
        )
        self.speaker_2_voice_menu.grid(
            row=3, column=1, sticky="ew", padx=(12, 0), pady=(12, 0)
        )

        ttk.Label(
            self.lesson_builder_card,
            text="Preview A",
        ).grid(row=4, column=0, sticky="w", pady=(14, 0), padx=(0, 6))
        ttk.Label(
            self.lesson_builder_card,
            text="Preview B",
        ).grid(row=4, column=1, sticky="w", pady=(14, 0), padx=(6, 0))

        self.lesson_structure_preview = tk.Text(
            self.lesson_builder_card,
            height=12,
            wrap=tk.WORD,
            bg="#10131a",
            fg="#eef2f8",
            insertbackground="#eef2f8",
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=10,
            font=("TkFixedFont", 11),
        )
        self.lesson_structure_preview.grid(
            row=5, column=0, sticky="nsew", pady=(6, 0), padx=(0, 6)
        )
        self.lesson_structure_preview.insert("1.0", LESSON_STRUCTURE_PLACEHOLDER)
        self.lesson_structure_preview.bind(
            "<KeyRelease>",
            lambda _event: self._update_lesson_comparison_summary(),
        )

        self.lesson_structure_preview_b = tk.Text(
            self.lesson_builder_card,
            height=12,
            wrap=tk.WORD,
            bg="#10131a",
            fg="#eef2f8",
            insertbackground="#eef2f8",
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=10,
            font=("TkFixedFont", 11),
        )
        self.lesson_structure_preview_b.grid(
            row=5, column=1, sticky="nsew", pady=(6, 0), padx=(6, 0)
        )
        self.lesson_structure_preview_b.bind(
            "<KeyRelease>",
            lambda _event: self._update_lesson_comparison_summary(),
        )

        ttk.Button(
            self.lesson_builder_card,
            text="Generate Lesson Structure",
            command=self._generate_lesson_structure,
        ).grid(row=6, column=0, sticky="ew", pady=(14, 0), padx=(0, 6))
        ttk.Button(
            self.lesson_builder_card,
            text="Duplicate Structure",
            command=self._duplicate_lesson_structure,
        ).grid(row=6, column=1, sticky="ew", pady=(14, 0), padx=(6, 0))
        ttk.Button(
            self.lesson_builder_card,
            text="Copy Structure",
            command=self._copy_lesson_structure,
        ).grid(row=7, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Label(
            self.lesson_builder_card,
            text="Comparison Summary",
        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(14, 0))
        ttk.Label(
            self.lesson_builder_card,
            textvariable=self.lesson_comparison_summary,
            style="Muted.TLabel",
            justify=tk.LEFT,
            wraplength=680,
        ).grid(row=9, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self._update_lesson_comparison_summary()

        self.conversion_card = self._create_card(content)
        self.conversion_card.grid(row=1, column=1, rowspan=3, sticky="nsew", padx=(8, 0))
        self.conversion_card.columnconfigure(0, weight=1)
        self.conversion_card.columnconfigure(1, weight=0)
        self._add_card_header(
            self.conversion_card,
            "Conversion",
            "Export your audiobook",
            "conversion",
        )

        ttk.Entry(self.conversion_card, textvariable=self.output_path).grid(
            row=1, column=0, sticky="ew", pady=(14, 10), padx=(0, 8)
        )
        ttk.Button(
            self.conversion_card,
            text="Save As",
            command=self._choose_output,
        ).grid(row=1, column=1, sticky="e", pady=(14, 10))

        self.progress_bar = AnimatedProgressBar(
            self.conversion_card,
            variable=self.progress_value,
        )
        self.progress_bar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 8))

        progress_meta = ttk.Frame(self.conversion_card, style="Card.TFrame")
        progress_meta.grid(row=3, column=0, columnspan=2, sticky="ew")
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
            wraplength=300,
        ).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(6, 12)
        )

        ToggleSwitch(
            self.conversion_card,
            text="Open audio automatically when finished",
            variable=self.open_audio_when_finished,
            background="#191c24",
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(0, 10))

        action_row = ttk.Frame(self.conversion_card, style="Card.TFrame")
        action_row.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(0, 10))
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
            text="Convert to MP3",
            style="Primary.TButton",
            command=self._start_conversion,
        )
        self.convert_button.grid(row=7, column=0, columnspan=2, sticky="ew")

        self._sync_lesson_builder_visibility()
        self._bind_scroll_events(self)

    def _create_card(self, parent: tk.Widget) -> ttk.Frame:
        """Create a dark card container."""

        card = ttk.Frame(parent, padding=16, style="Card.TFrame")
        return card

    def _update_scroll_region(self, _event: tk.Event) -> None:
        """Keep the scrollable content region aligned with its children."""

        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))

    def _resize_scroll_content(self, event: tk.Event) -> None:
        """Resize the inner content frame to the visible canvas width."""

        self.content_canvas.itemconfigure(self.content_window, width=event.width)
        self._reflow_cards(event.width)

    def _reflow_cards(self, width: int) -> None:
        """Switch cards between two-column and single-column layouts."""

        if width < 820:
            self.pdf_card.grid_configure(row=0, column=0, padx=0, pady=(0, 12))
            self.voices_card.grid_configure(row=1, column=0, padx=0, pady=(0, 12))
            self.learning_card.grid_configure(row=2, column=0, padx=0, pady=(0, 12))
            self.mode_card.grid_configure(row=3, column=0, padx=0, pady=(0, 12))
            self.lesson_builder_card.grid_configure(
                row=4, column=0, padx=0, pady=(0, 12)
            )
            self.conversion_card.grid_configure(
                row=5, column=0, rowspan=1, padx=0, pady=(0, 0)
            )
        else:
            self.pdf_card.grid_configure(row=0, column=0, padx=(0, 8), pady=(0, 12))
            self.voices_card.grid_configure(row=0, column=1, padx=(8, 0), pady=(0, 12))
            self.learning_card.grid_configure(row=1, column=0, padx=(0, 8), pady=(0, 12))
            self.mode_card.grid_configure(row=2, column=0, padx=(0, 8), pady=(0, 12))
            self.lesson_builder_card.grid_configure(
                row=3, column=0, padx=(0, 8), pady=(0, 0)
            )
            self.conversion_card.grid_configure(
                row=1, column=1, rowspan=3, padx=(8, 0), pady=(0, 0)
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
        title: str,
        subtitle: str,
        icon_name: str,
    ) -> None:
        """Add a section title, subtitle, and simple drawn icon."""

        icon = tk.Canvas(
            parent,
            width=48,
            height=48,
            bg="#191c24",
            highlightthickness=0,
            bd=0,
        )
        icon.grid(row=0, column=0, sticky="w", padx=(0, 14))
        self._draw_icon(icon, icon_name)

        title_frame = ttk.Frame(parent, style="Card.TFrame")
        title_frame.grid(row=0, column=1, columnspan=2, sticky="ew")
        ttk.Label(title_frame, text=title, style="Section.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(title_frame, text=subtitle, style="Muted.TLabel").grid(
            row=1, column=0, sticky="w", pady=(2, 0)
        )

    def _draw_icon(self, canvas: tk.Canvas, icon_name: str) -> None:
        """Draw small section icons without external image dependencies."""

        accent = "#1db954"
        muted = "#9aa4b2"
        canvas.create_oval(2, 2, 46, 46, fill="#10131a", outline="#303644", width=1)

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

        english_labels = [option.label for option in self._english_voice_options]
        spanish_labels = [option.label for option in self._spanish_voice_options]
        speaker_labels = [option.label for option in self._all_voice_options()]

        self.english_voice_menu.configure(values=english_labels or [DEFAULT_ENGLISH_VOICE])
        self.spanish_voice_menu.configure(values=spanish_labels or [DEFAULT_SPANISH_VOICE])
        self.speaker_1_voice_menu.configure(
            values=speaker_labels or [DEFAULT_ENGLISH_VOICE]
        )
        self.speaker_2_voice_menu.configure(
            values=speaker_labels or [DEFAULT_SPANISH_VOICE]
        )
        self.selected_english_voice.set(DEFAULT_ENGLISH_VOICE)
        self.selected_spanish_voice.set(DEFAULT_SPANISH_VOICE)
        self.selected_speaker_1_voice.set(DEFAULT_ENGLISH_VOICE)
        self.selected_speaker_2_voice.set(DEFAULT_SPANISH_VOICE)

    def _load_settings(self) -> None:
        """Load saved settings from disk, ignoring missing or invalid files."""

        if not SETTINGS_FILE.exists():
            return

        try:
            settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(settings, dict):
            return

        self._is_loading_settings = True
        try:
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
            conversion_mode = str(
                settings.get("conversion_mode", DEFAULT_CONVERSION_MODE)
            ).lower()
            if conversion_mode in CONVERSION_MODE_OPTIONS.values():
                self.selected_conversion_mode.set(
                    self._conversion_mode_label_for_value(conversion_mode)
                )
                self._update_conversion_mode_description()
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
        finally:
            self._is_loading_settings = False

    def _attach_settings_traces(self) -> None:
        """Save settings whenever persistent UI state changes."""

        watched_variables = [
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
            self.auto_detect_language,
            self.default_untagged_language,
            self.open_audio_when_finished,
        ]
        for variable in watched_variables:
            variable.trace_add("write", lambda *_args: self._save_settings())

    def _settings_payload(self) -> dict[str, Any]:
        """Return the configuration values safe to persist."""

        return {
            "english_voice": self.selected_english_voice.get(),
            "spanish_voice": self.selected_spanish_voice.get(),
            "speaker_1_voice": self.selected_speaker_1_voice.get(),
            "speaker_2_voice": self.selected_speaker_2_voice.get(),
            "speech_rate": self.selected_rate_label.get(),
            "volume": self.selected_volume_label.get(),
            "conversion_mode": self._conversion_mode_value(),
            "auto_learning_pauses": bool(self.auto_learning_pauses.get()),
            "auto_pause_seconds": int(self.auto_pause_seconds.get()),
            "auto_pause_segmentation": self._auto_pause_segmentation_value(),
            "auto_detect_language": bool(self.auto_detect_language.get()),
            "default_untagged_language": self._default_untagged_language_code(),
            "open_audio_when_finished": bool(self.open_audio_when_finished.get()),
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
                self.output_path.set(str(pdf_path.with_suffix(".mp3")))
                self._last_output_folder = str(pdf_path.parent)
            self._apply_page_count(page_count)
            self.pdf_select_area.set_selected_file(pdf_path.name)
            self._save_settings()

    def _choose_output(self) -> None:
        """Ask the user where the MP3 should be saved."""

        initial_file = "audiobook.mp3"
        if self.pdf_path.get():
            initial_file = f"{Path(self.pdf_path.get()).stem}.mp3"
        initial_directory = self._last_output_folder or None

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
        self.status_text.set("PDF loaded. Choose the output file and convert.")

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
        self.preview_button.configure(state=tk.DISABLED)
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
            self.convert_button.configure(text="Convert to MP3")
        self._sync_lesson_builder_visibility()

    def _sync_lesson_builder_visibility(self) -> None:
        """Show the builder foundation only for EchoLesson Mode."""

        if self._conversion_mode_value() == "echolesson":
            self.lesson_builder_card.grid()
        else:
            self.lesson_builder_card.grid_remove()

    def _generate_lesson_structure(self) -> None:
        """Generate deterministic EchoLearn Markup from the selected PDF."""

        if not self.pdf_path.get():
            messagebox.showerror(
                "Missing PDF",
                "Please select a PDF before generating lesson structure.",
            )
            return

        pdf_path = Path(self.pdf_path.get())
        if not pdf_path.exists():
            messagebox.showerror(
                "Missing PDF",
                "The selected PDF file does not exist.",
            )
            return

        try:
            pdf_text = extract_text_from_pdf(pdf_path, lambda _page, _total: None)
            lesson_builder = LessonBuilder()
            generated_structure, lesson_analysis = (
                lesson_builder.generate_structure_with_analysis(pdf_text)
            )
        except PDFAudiobookError as exc:
            messagebox.showerror("Could not generate lesson structure", str(exc))
            return
        except Exception as exc:
            traceback.print_exc()
            messagebox.showerror(
                "Could not generate lesson structure",
                "EchoLearn could not generate a lesson structure from this PDF.",
            )
            return

        if not generated_structure:
            messagebox.showerror(
                "Could not generate lesson structure",
                "No usable text was found for lesson structure generation.",
            )
            return

        self._set_lesson_structure_preview(generated_structure)
        print(lesson_analysis.format())
        self.status_text.set(
            "Lesson structure preview generated. "
            f"Title: {lesson_analysis.title_count}, "
            f"Explanation: {lesson_analysis.explanation_count}, "
            f"Flow: {lesson_analysis.flow_count}, "
            f"Dialogues: {lesson_analysis.dialogue_count}, "
            f"Practice: {lesson_analysis.practice_count}, "
            f"Review: {lesson_analysis.review_count}."
        )

    def _set_lesson_structure_preview(self, markup: str) -> None:
        """Replace the editable lesson structure preview text."""

        self.lesson_structure_preview.configure(state=tk.NORMAL)
        self.lesson_structure_preview.delete("1.0", tk.END)
        self.lesson_structure_preview.insert("1.0", markup)
        self._update_lesson_comparison_summary()

    def _lesson_structure_markup(self) -> str:
        """Return the edited EchoLesson markup from Preview A."""

        return self.lesson_structure_preview.get("1.0", tk.END).strip()

    def _lesson_structure_markup_b(self) -> str:
        """Return the edited EchoLesson markup from Preview B."""

        return self.lesson_structure_preview_b.get("1.0", tk.END).strip()

    def _duplicate_lesson_structure(self) -> None:
        """Copy Preview A into Preview B for side-by-side comparison."""

        markup = self._lesson_structure_markup()
        self.lesson_structure_preview_b.configure(state=tk.NORMAL)
        self.lesson_structure_preview_b.delete("1.0", tk.END)
        self.lesson_structure_preview_b.insert("1.0", markup)
        self._update_lesson_comparison_summary()
        self.status_text.set("Preview A duplicated into Preview B.")

    def _copy_lesson_structure(self) -> None:
        """Copy generated lesson markup from Preview A to the clipboard."""

        markup = self._lesson_structure_markup()
        if not markup:
            return
        self.clipboard_clear()
        self.clipboard_append(markup)
        self.status_text.set("Lesson structure copied to clipboard.")

    def _update_lesson_comparison_summary(self) -> None:
        """Refresh the simple Preview A/B structure comparison."""

        self.lesson_comparison_summary.set(
            self._format_lesson_comparison_summary(
                self._lesson_structure_markup(),
                self._lesson_structure_markup_b(),
            )
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
            "Preview A\n"
            f"- Dialogues: {preview_a_counts['dialogues']}\n"
            f"- Practice: {preview_a_counts['practice']}\n"
            f"- Review: {preview_a_counts['review']}\n\n"
            "Preview B\n"
            f"- Dialogues: {preview_b_counts['dialogues']}\n"
            f"- Practice: {preview_b_counts['practice']}\n"
            f"- Review: {preview_b_counts['review']}"
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
        self.preview_button.configure(state=tk.NORMAL)


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
