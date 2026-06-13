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


APP_TITLE = "PDF Audiobook Converter"
DEFAULT_RATE = 0
DEFAULT_VOLUME = 0
DEFAULT_ENGLISH_VOICE = "en-US-JennyNeural"
DEFAULT_SPANISH_VOICE = "es-CO-SalomeNeural"
DEFAULT_SHADOWING_PAUSE_SECONDS = 3
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


class PDFAudiobookApp(tk.Tk):
    """Main Tkinter window for the PDF audiobook converter."""

    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("720x560")
        self.minsize(660, 520)

        self.pdf_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.page_count = tk.StringVar(value="Pages: 0")
        self.status_text = tk.StringVar(value="Choose a PDF to begin.")
        self.selected_english_voice = tk.StringVar(value=DEFAULT_ENGLISH_VOICE)
        self.selected_spanish_voice = tk.StringVar(value=DEFAULT_SPANISH_VOICE)
        self.rate = tk.IntVar(value=DEFAULT_RATE)
        self.volume = tk.IntVar(value=DEFAULT_VOLUME)
        self.shadowing_mode = tk.BooleanVar(value=False)
        self.progress_value = tk.DoubleVar(value=0)

        self._messages: queue.Queue[ProgressMessage] = queue.Queue()
        self._english_voice_options: list[VoiceOption] = []
        self._spanish_voice_options: list[VoiceOption] = []
        self._is_processing = False

        self._configure_style()
        self._build_ui()
        self._load_voices()
        self.after(100, self._process_worker_messages)

    def _configure_style(self) -> None:
        """Apply a clean cross-platform ttk theme."""

        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TButton", padding=(12, 8))
        style.configure("TLabel", padding=(0, 3))
        style.configure("Title.TLabel", font=("TkDefaultFont", 18, "bold"))
        style.configure("Status.TLabel", foreground="#2f5d62")

    def _build_ui(self) -> None:
        """Create all visual controls."""

        container = ttk.Frame(self, padding=24)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(0, weight=1)

        ttk.Label(container, text=APP_TITLE, style="Title.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 18)
        )

        file_frame = ttk.LabelFrame(container, text="PDF file", padding=14)
        file_frame.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        file_frame.columnconfigure(0, weight=1)

        ttk.Entry(file_frame, textvariable=self.pdf_path).grid(
            row=0, column=0, sticky="ew", padx=(0, 8)
        )
        ttk.Button(file_frame, text="Browse", command=self._choose_pdf).grid(
            row=0, column=1
        )
        ttk.Label(file_frame, textvariable=self.page_count).grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )

        output_frame = ttk.LabelFrame(container, text="MP3 output", padding=14)
        output_frame.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        output_frame.columnconfigure(0, weight=1)

        ttk.Entry(output_frame, textvariable=self.output_path).grid(
            row=0, column=0, sticky="ew", padx=(0, 8)
        )
        ttk.Button(output_frame, text="Save As", command=self._choose_output).grid(
            row=0, column=1
        )

        settings_frame = ttk.LabelFrame(container, text="Speech settings", padding=14)
        settings_frame.grid(row=3, column=0, sticky="ew", pady=(0, 14))
        settings_frame.columnconfigure(1, weight=1)

        ttk.Label(settings_frame, text="English voice").grid(row=0, column=0, sticky="w")
        self.english_voice_menu = ttk.Combobox(
            settings_frame,
            textvariable=self.selected_english_voice,
            state="readonly",
            values=[],
        )
        self.english_voice_menu.grid(row=0, column=1, sticky="ew", padx=(12, 0))

        ttk.Label(settings_frame, text="Spanish voice").grid(
            row=1, column=0, sticky="w", pady=(12, 0)
        )
        self.spanish_voice_menu = ttk.Combobox(
            settings_frame,
            textvariable=self.selected_spanish_voice,
            state="readonly",
            values=[],
        )
        self.spanish_voice_menu.grid(
            row=1, column=1, sticky="ew", padx=(12, 0), pady=(12, 0)
        )

        self.preview_button = ttk.Button(
            settings_frame,
            text="Preview Voice",
            command=self._start_voice_preview,
        )
        self.preview_button.grid(
            row=2, column=1, sticky="w", padx=(12, 0), pady=(12, 0)
        )

        ttk.Label(settings_frame, text="Speech rate").grid(
            row=3, column=0, sticky="w", pady=(12, 0)
        )
        ttk.Scale(
            settings_frame,
            from_=-50,
            to=50,
            orient=tk.HORIZONTAL,
            variable=self.rate,
        ).grid(row=3, column=1, sticky="ew", padx=(12, 0), pady=(12, 0))
        ttk.Label(settings_frame, textvariable=self.rate).grid(
            row=3, column=2, sticky="e", padx=(10, 0), pady=(12, 0)
        )

        ttk.Label(settings_frame, text="Volume").grid(
            row=4, column=0, sticky="w", pady=(12, 0)
        )
        ttk.Scale(
            settings_frame,
            from_=-50,
            to=50,
            orient=tk.HORIZONTAL,
            variable=self.volume,
        ).grid(row=4, column=1, sticky="ew", padx=(12, 0), pady=(12, 0))
        ttk.Label(settings_frame, textvariable=self.volume).grid(
            row=4, column=2, sticky="e", padx=(10, 0), pady=(12, 0)
        )

        ttk.Checkbutton(
            settings_frame,
            text="Shadowing Mode",
            variable=self.shadowing_mode,
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(12, 0))

        progress_frame = ttk.Frame(container)
        progress_frame.grid(row=4, column=0, sticky="ew", pady=(2, 16))
        progress_frame.columnconfigure(0, weight=1)

        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_value,
            maximum=100,
            mode="determinate",
        )
        self.progress_bar.grid(row=0, column=0, sticky="ew")

        ttk.Label(container, textvariable=self.status_text, style="Status.TLabel").grid(
            row=5, column=0, sticky="w"
        )

        action_frame = ttk.Frame(container)
        action_frame.grid(row=6, column=0, sticky="e", pady=(20, 0))

        self.convert_button = ttk.Button(
            action_frame,
            text="Convert to MP3",
            command=self._start_conversion,
        )
        self.convert_button.pack(side=tk.RIGHT)

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

        self.pdf_path.set(path)
        if not self.output_path.get():
            self.output_path.set(str(Path(path).with_suffix(".mp3")))
        self._update_page_count(Path(path))

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

    def _update_page_count(self, pdf_path: Path) -> None:
        """Read and display the number of pages in the selected PDF."""

        try:
            reader = PdfReader(str(pdf_path))
            count = len(reader.pages)
        except Exception as exc:
            traceback.print_exc()
            raise

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
        self.progress_value.set(0)
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
        self.progress_value.set(0)
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

    def _run_conversion(self, settings: ConversionSettings) -> None:
        """Worker-thread conversion body."""

        try:
            self._messages.put(ProgressMessage("status", "Extracting text from PDF..."))

            def progress_callback(page: int, total: int) -> None:
                percent = (page / total) * 70
                self._messages.put(ProgressMessage("progress", percent))
                self._messages.put(
                    ProgressMessage("status", f"Extracting page {page} of {total}...")
                )

            text = extract_text_from_pdf(settings.pdf_path, progress_callback)
            if DEBUG_MODE:
                write_debug_text(text, DEBUG_NORMALIZED_TEXT_FILE)

            segments, warnings = parse_audio_script(text)
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
                progress_callback=lambda current, total: self._messages.put(
                    ProgressMessage("progress", 70 + (current / total) * 28)
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
                    self.progress_value.set(float(message.payload))
                elif message.kind == "status":
                    self.status_text.set(str(message.payload))
                elif message.kind == "success":
                    self._finish_processing()
                    result = message.payload
                    path = Path(result.output_path)
                    self.status_text.set(f"Done: {path}")
                    warning_text = ""
                    if result.warnings:
                        warning_text = "\n\nWarnings:\n" + "\n".join(result.warnings)
                    messagebox.showinfo(
                        "Audiobook created",
                        f"Your audiobook was saved successfully:\n\n{path}{warning_text}",
                    )
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
        self.convert_button.configure(state=tk.NORMAL)
        self.preview_button.configure(state=tk.NORMAL)


def main() -> None:
    """Application entry point."""

    app = PDFAudiobookApp()
    app.mainloop()


if __name__ == "__main__":
    main()
