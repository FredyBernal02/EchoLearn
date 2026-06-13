"""Desktop PDF to audiobook converter.

This module provides a Tkinter application that extracts text from a PDF with
pypdf and converts it to an MP3 audiobook using edge-tts.
"""

from __future__ import annotations

import asyncio
import os
import platform
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import tkinter as tk
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

import edge_tts
from pypdf import PdfReader
from pypdf.errors import PdfReadError

APP_TITLE = "EchoLearn"
DEFAULT_RATE = 0
DEFAULT_VOLUME = 0
DEFAULT_ENGLISH_VOICE = "en-US-JennyNeural"
DEFAULT_SPANISH_VOICE = "es-CO-SalomeNeural"
DEFAULT_SHADOWING_PAUSE_SECONDS = 3
DEFAULT_LEARNING_PAUSES_ENABLED = True
DEFAULT_LEARNING_PAUSE_SECONDS = 2
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
SUPPORTED_PAUSES = {1, 2, 3, 5, 10}
TAG_PATTERN = re.compile(r"\[(EN|ES|PAUSE_(\d+)|PAUSE_[^\]]+)\]", re.IGNORECASE)
TAG_ONLY_PATTERN = re.compile(r"^\[(EN|ES|PAUSE_\d+)\]$", re.IGNORECASE)
DEBUG_MODE = True
DEBUG_SEGMENTS_FILE = Path("debug_segments.txt")
DEBUG_NORMALIZED_TEXT_FILE = Path("debug_normalized_text.txt")


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

    pdf_path: Path
    output_path: Path
    english_voice_id: str
    spanish_voice_id: str
    rate: int
    volume: int
    shadowing_mode: bool
    idioms_mode: bool
    learning_pauses: bool
    learning_pause_seconds: int


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
    language: str = "EN"
    seconds: int = 0


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


def parse_audio_script(text: str) -> tuple[list[ScriptSegment], list[str]]:
    """Turn PDF text with [EN], [ES], and [PAUSE_X] tags into audio requests."""

    segments: list[ScriptSegment] = []
    warnings: list[str] = []
    current_language = "EN"
    position = 0

    def add_text_segment(raw_text: str) -> None:
        cleaned_text = normalize_text(raw_text)
        if cleaned_text:
            if TAG_ONLY_PATTERN.fullmatch(cleaned_text):
                return
            segments.append(
                ScriptSegment(
                    kind="text",
                    text=cleaned_text,
                    language=current_language,
                )
            )

    for match in TAG_PATTERN.finditer(text):
        add_text_segment(text[position : match.start()])

        tag = match.group(1).upper()
        pause_seconds = match.group(2)

        if tag in {"EN", "ES"}:
            current_language = tag
        elif pause_seconds and int(pause_seconds) in SUPPORTED_PAUSES:
            segments.append(
                ScriptSegment(kind="pause", seconds=int(pause_seconds))
            )
        else:
            warnings.append(f"Ignored unsupported pause tag [{tag}].")

        position = match.end()

    add_text_segment(text[position:])
    return segments, warnings


def add_shadowing_repeats(segments: list[ScriptSegment]) -> list[ScriptSegment]:
    """Repeat English text segments after a short pause for shadowing practice."""

    shadowed_segments: list[ScriptSegment] = []
    for index, segment in enumerate(segments, start=1):
        shadowed_segments.append(segment)
        if segment.kind == "text" and segment.language == "EN":
            print(f"Adding shadowing repeat for segment {index}")
            shadowed_segments.append(
                ScriptSegment(
                    kind="pause",
                    seconds=DEFAULT_SHADOWING_PAUSE_SECONDS,
                )
            )
            shadowed_segments.append(segment)

    return shadowed_segments


def add_idiom_repeats(
    segments: list[ScriptSegment],
    *,
    learning_pauses: bool,
    learning_pause_seconds: int,
) -> list[ScriptSegment]:
    """Repeat English once after each consecutive English/Spanish text pair."""

    idiom_segments: list[ScriptSegment] = []
    learning_pause = ScriptSegment(kind="pause", seconds=learning_pause_seconds)
    index = 0
    while index < len(segments):
        current_segment = segments[index]
        next_segment = segments[index + 1] if index + 1 < len(segments) else None

        is_idiom_pair = (
            current_segment.kind == "text"
            and current_segment.language == "EN"
            and next_segment is not None
            and next_segment.kind == "text"
            and next_segment.language == "ES"
        )
        if is_idiom_pair:
            print(f"Adding idiom repeat for segment {index + 1}")
            if learning_pauses:
                print(f"Adding learning pauses: {learning_pause_seconds} seconds")
                idiom_segments.extend(
                    [
                        current_segment,
                        learning_pause,
                        next_segment,
                        learning_pause,
                        current_segment,
                    ]
                )
            else:
                idiom_segments.extend([current_segment, next_segment, current_segment])
            index += 2
            continue

        idiom_segments.append(current_segment)
        index += 1

    return idiom_segments


def write_debug_segments(segments: list[ScriptSegment], debug_path: Path) -> None:
    """Write parsed segments to a debug file before audio generation starts."""

    with debug_path.open("w", encoding="utf-8") as debug_file:
        for index, segment in enumerate(segments, start=1):
            debug_file.write(f"Segment {index}\n")
            debug_file.write(f"kind={segment.kind}\n")
            debug_file.write(f"language={segment.language}\n")
            debug_file.write(f"seconds={segment.seconds}\n")
            debug_file.write(f"text={segment.text!r}\n")
            debug_file.write("\n")


def write_debug_text(text: str, debug_path: Path) -> None:
    """Write normalized extracted text before parsing starts."""

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

        with tempfile.TemporaryDirectory(prefix="pdf-audiobook-") as temp_folder:
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

                    voice_id = (
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

        command = [
            "ffmpeg",
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
            raise PDFAudiobookError(
                "FFmpeg is required to generate real pauses. Please install it with: "
                "brew install ffmpeg"
            ) from exc
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


class PDFAudiobookApp(tk.Tk):
    """Main Tkinter window for the PDF audiobook converter."""

    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("940x680")
        self.minsize(720, 520)

        self.pdf_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.page_count = tk.StringVar(value="Pages: 0")
        self.status_text = tk.StringVar(value="Choose a PDF to begin.")
        self.selected_english_voice = tk.StringVar(value=DEFAULT_ENGLISH_VOICE)
        self.selected_spanish_voice = tk.StringVar(value=DEFAULT_SPANISH_VOICE)
        self.rate = tk.IntVar(value=DEFAULT_RATE)
        self.volume = tk.IntVar(value=DEFAULT_VOLUME)
        self.selected_rate_label = tk.StringVar(value="Normal")
        self.selected_volume_label = tk.StringVar(value="Normal")
        self.shadowing_mode = tk.BooleanVar(value=False)
        self.idioms_mode = tk.BooleanVar(value=False)
        self.learning_pauses = tk.BooleanVar(value=DEFAULT_LEARNING_PAUSES_ENABLED)
        self.learning_pause_seconds = tk.IntVar(value=DEFAULT_LEARNING_PAUSE_SECONDS)
        self.open_audio_when_finished = tk.BooleanVar(value=False)
        self.progress_value = tk.DoubleVar(value=0)
        self.progress_percent = tk.StringVar(value="0%")

        self._messages: queue.Queue[ProgressMessage] = queue.Queue()
        self._english_voice_options: list[VoiceOption] = []
        self._spanish_voice_options: list[VoiceOption] = []
        self._is_processing = False
        self._last_output_path: Path | None = None

        self._configure_style()
        self._build_ui()
        self._load_voices()
        self.after(100, self._process_worker_messages)

    def _configure_style(self) -> None:
        """Apply a polished dark desktop theme."""

        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        self.configure(bg="#0f1117")

        style.configure("App.TFrame", background="#0f1117")
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
            "Horizontal.TProgressbar",
            background="#1db954",
            troughcolor="#242833",
            bordercolor="#242833",
            lightcolor="#1db954",
            darkcolor="#1db954",
            thickness=12,
        )
    def _build_ui(self) -> None:
        """Create all visual controls."""

        container = ttk.Frame(self, padding=(20, 18), style="App.TFrame")
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)

        header = ttk.Frame(container, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text="EchoLearn", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(header, text="Learn by Listening", style="Subtitle.TLabel").grid(
            row=1, column=0, sticky="w", pady=(5, 0)
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
            text="Shadowing Mode",
            variable=self.shadowing_mode,
            background="#191c24",
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(14, 0))

        ToggleSwitch(
            self.learning_card,
            text="Idioms Mode",
            variable=self.idioms_mode,
            background="#191c24",
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))

        ToggleSwitch(
            self.learning_card,
            text="Learning Pauses",
            variable=self.learning_pauses,
            background="#191c24",
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 0))

        ttk.Label(self.learning_card, text="Learning pause seconds").grid(
            row=6, column=0, sticky="w", pady=(10, 0)
        )
        self.learning_pause_menu = ttk.Combobox(
            self.learning_card,
            textvariable=self.learning_pause_seconds,
            state="readonly",
            values=[1, 2, 3, 5],
            width=6,
        )
        self.learning_pause_menu.grid(
            row=6, column=1, sticky="w", padx=(12, 0), pady=(10, 0)
        )

        self.conversion_card = self._create_card(content)
        self.conversion_card.grid(row=1, column=1, sticky="nsew", padx=(8, 0))
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

        self.open_folder_button = ttk.Button(
            action_row,
            text="Open Folder",
            command=self._open_last_output_folder,
        )
        self.open_folder_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self.open_folder_button.configure(state=tk.DISABLED)

        self.convert_button = ttk.Button(
            self.conversion_card,
            text="Convert to MP3",
            style="Primary.TButton",
            command=self._start_conversion,
        )
        self.convert_button.grid(row=7, column=0, columnspan=2, sticky="ew")

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
            self.conversion_card.grid_configure(row=3, column=0, padx=0, pady=(0, 0))
        else:
            self.pdf_card.grid_configure(row=0, column=0, padx=(0, 8), pady=(0, 12))
            self.voices_card.grid_configure(row=0, column=1, padx=(8, 0), pady=(0, 12))
            self.learning_card.grid_configure(row=1, column=0, padx=(0, 8), pady=(0, 0))
            self.conversion_card.grid_configure(row=1, column=1, padx=(8, 0), pady=(0, 0))

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

        self.english_voice_menu.configure(values=english_labels or [DEFAULT_ENGLISH_VOICE])
        self.spanish_voice_menu.configure(values=spanish_labels or [DEFAULT_SPANISH_VOICE])
        self.selected_english_voice.set(DEFAULT_ENGLISH_VOICE)
        self.selected_spanish_voice.set(DEFAULT_SPANISH_VOICE)

    def _choose_pdf(self) -> None:
        """Ask the user to select a PDF file and show the page count."""

        path = filedialog.askopenfilename(
            title="Select a PDF file",
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
            if not self.output_path.get():
                self.output_path.set(str(pdf_path.with_suffix(".mp3")))
            self._apply_page_count(page_count)
            self.pdf_select_area.set_selected_file(pdf_path.name)

    def _choose_output(self) -> None:
        """Ask the user where the MP3 should be saved."""

        initial_file = "audiobook.mp3"
        if self.pdf_path.get():
            initial_file = f"{Path(self.pdf_path.get()).stem}.mp3"

        path = filedialog.asksaveasfilename(
            title="Save audiobook as",
            defaultextension=".mp3",
            initialfile=initial_file,
            filetypes=[("MP3 files", "*.mp3"), ("All files", "*.*")],
        )
        if path:
            self.output_path.set(path)

    def _open_last_audio(self) -> None:
        """Open the most recently generated MP3."""

        if self._last_output_path is None:
            return
        try:
            self._open_path(self._last_output_path)
        except PDFAudiobookError as exc:
            messagebox.showerror("Could not open audio", str(exc))

    def _open_last_output_folder(self) -> None:
        """Open the folder containing the most recently generated MP3."""

        if self._last_output_path is None:
            return
        try:
            self._open_path(self._last_output_path.parent)
        except PDFAudiobookError as exc:
            messagebox.showerror("Could not open folder", str(exc))

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

        try:
            settings = self._get_settings()
        except ValueError as exc:
            messagebox.showerror("Missing information", str(exc))
            return

        self._is_processing = True
        self.convert_button.configure(state=tk.DISABLED)
        self.open_audio_button.configure(state=tk.DISABLED)
        self.open_folder_button.configure(state=tk.DISABLED)
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

        return ConversionSettings(
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
            shadowing_mode=bool(self.shadowing_mode.get()),
            idioms_mode=bool(self.idioms_mode.get()),
            learning_pauses=bool(self.learning_pauses.get()),
            learning_pause_seconds=int(self.learning_pause_seconds.get()),
        )

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

    def _update_rate_from_label(self, _event: tk.Event | None = None) -> None:
        """Map the selected speech-rate label to the internal TTS value."""

        self.rate.set(RATE_OPTIONS.get(self.selected_rate_label.get(), DEFAULT_RATE))

    def _update_volume_from_label(self, _event: tk.Event | None = None) -> None:
        """Map the selected volume label to the internal TTS value."""

        self.volume.set(
            VOLUME_OPTIONS.get(self.selected_volume_label.get(), DEFAULT_VOLUME)
        )

    def _set_progress(self, percent: float) -> None:
        """Update progress value and percentage label together."""

        bounded_percent = max(0.0, min(percent, 100.0))
        self.progress_value.set(bounded_percent)
        self.progress_percent.set(f"{bounded_percent:.0f}%")

    def _run_conversion(self, settings: ConversionSettings) -> None:
        """Worker-thread conversion body."""

        try:
            self._messages.put(ProgressMessage("status", "Processing PDF..."))

            def progress_callback(page: int, total: int) -> None:
                percent = (page / total) * 70
                self._messages.put(ProgressMessage("progress", percent))
                self._messages.put(
                    ProgressMessage("status", f"Processing page {page} of {total}")
                )

            text = extract_text_from_pdf(settings.pdf_path, progress_callback)
            if DEBUG_MODE:
                write_debug_text(text, DEBUG_NORMALIZED_TEXT_FILE)

            segments, warnings = parse_audio_script(text)
            print(f"Idioms Mode: {'ON' if settings.idioms_mode else 'OFF'}")
            if settings.idioms_mode:
                segments = add_idiom_repeats(
                    segments,
                    learning_pauses=settings.learning_pauses,
                    learning_pause_seconds=settings.learning_pause_seconds,
                )
            print(f"Shadowing Mode: {'ON' if settings.shadowing_mode else 'OFF'}")
            if settings.shadowing_mode:
                segments = add_shadowing_repeats(segments)
            if DEBUG_MODE:
                write_debug_segments(segments, DEBUG_SEGMENTS_FILE)

            self._messages.put(
                ProgressMessage(
                    "status",
                    "Creating full audiobook MP3...",
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
            fd, path = tempfile.mkstemp(prefix="echolearn-preview-", suffix=".mp3")
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
                    self.open_folder_button.configure(state=tk.NORMAL)
                    self.status_text.set(f"Done: {path}")
                    warning_text = ""
                    if result.warnings:
                        warning_text = "\n\nWarnings:\n" + "\n".join(result.warnings)
                    messagebox.showinfo(
                        "Audiobook created",
                        f"Your audiobook was saved successfully:\n\n{path}{warning_text}",
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

    app = PDFAudiobookApp()
    app.mainloop()


if __name__ == "__main__":
    main()
