# EchoLearn

Convert PDFs into natural-sounding audiobooks using Microsoft Edge TTS voices, bilingual narration, and real FFmpeg-generated pauses.

A cross-platform desktop app that converts selectable-text PDF files into MP3 audiobooks.

The app supports simple script tags inside the PDF text, so one audiobook can switch between English and Spanish voices and include timed pauses.

## Features

- Tkinter graphical interface
- PDF text extraction with `pypdf`
- Text-to-speech MP3 generation with `edge-tts`
- Real timed pause generation with FFmpeg
- English and Spanish voice selectors
- Voice Preview for selected voices and speech settings
- Speech rate and volume controls
- Shadowing Mode for automatic English phrase repetition
- Idioms Mode for English-Spanish-English learning patterns
- Learning Pauses for timed practice gaps in Idioms Mode
- Modern dark interface with toggle switches
- Official EchoLearn logo in the app header
- Clickable PDF selection area with Browse PDF fallback
- Detailed progress with page, segment, and percentage updates
- Open Audio and Open Folder actions after conversion
- MP3 output file selection
- Page count display and progress bar
- Friendly error messages for invalid, empty, scanned, or image-only PDFs

## Project Structure

```text
EchoLearn/
├── assets/
│   ├── echolearn_logo.png
│   └── echolearn.icns
├── main.py
├── requirements.txt
├── README.md
└── .gitignore
```

## Installation

1. Open a terminal in the project folder.

2. Create and activate a virtual environment.

   Windows:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

   macOS and Linux:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install the Python dependencies:

   ```bash
   pip install -r requirements.txt
   ```

## Running the App

From inside the `pdf_audiobook` folder, run:

```bash
python main.py
```

On some macOS or Linux installations, use:

```bash
python3 main.py
```

## Logo and macOS App Icon

The official EchoLearn logo lives at:

```text
assets/echolearn_logo.png
```

The macOS app icon is generated from that PNG and saved as:

```text
assets/echolearn.icns
```

Build the macOS app with PyInstaller using the icon:

```bash
/usr/local/bin/python3 -m PyInstaller --windowed --name EchoLearn --icon assets/echolearn.icns --add-data assets:assets main.py
```

To regenerate the icon after replacing `assets/echolearn_logo.png`, run:

```bash
/usr/local/bin/python3 scripts/create_macos_icon.py
```

This creates all required files in `assets/echolearn.iconset/` and writes
`assets/echolearn.icns`.

To verify PyInstaller accepts the icon without touching the normal `dist/`
folder, run:

```bash
/usr/local/bin/python3 -m PyInstaller --noconfirm --windowed --name EchoLearn --icon "$(pwd)/assets/echolearn.icns" --add-data "$(pwd)/assets:assets" --distpath /private/tmp/echolearn-pyi-verify-dist --workpath /private/tmp/echolearn-pyi-verify-build --specpath /private/tmp/echolearn-pyi-verify-spec main.py
```

If Finder still shows an old icon after rebuilding, delete the previous
`build/` and `dist/` folders, rebuild the app, and reopen Finder.

## Usage

1. Click the PDF selection area or click **Browse PDF** and choose a PDF file.
2. Confirm the page count shown by the app.
3. Click **Save As** and choose where to save the MP3 audiobook.
4. Select an English voice and a Spanish voice.
5. Adjust speech rate and volume.
6. Optionally enable **Shadowing Mode** for English pronunciation practice.
7. Click **Convert to MP3**.
8. Follow the progress percentage, current page, and current segment updates.
9. Use **Open Audio** or **Open Folder** after conversion, or enable **Open audio automatically when finished**.

## Interface

EchoLearn uses a dark, card-based desktop interface with modern toggle switches
for learning modes, larger controls, and a progress area that shows both the
current task and percentage completed.

The PDF section includes a clickable selection area and a **Browse PDF** button.
Both open the same file picker and load the selected PDF.

Speech rate uses simple dropdown options: **Very Slow**, **Slow**, **Normal**,
**Fast**, and **Very Fast**. Volume uses **Very Low**, **Low**, **Normal**,
**High**, and **Very High**.

## Writing PDF Scripts

Add tags directly in your PDF text to control the audiobook.

Use `[EN]` before English text:

```text
[EN] To take care.
```

Use `[ES]` before Spanish text:

```text
[ES] Cuidar.
```

Use pause tags to insert real silent pauses:

```text
[PAUSE_3]
[PAUSE_5]
```

Supported pause tags are:

```text
[PAUSE_1]
[PAUSE_2]
[PAUSE_3]
[PAUSE_5]
[PAUSE_10]
```

Internally, the app asks FFmpeg to create silent MP3 segments and inserts them
between speech segments.

Example script:

```text
[EN] To take care.
[ES] Cuidar.
[PAUSE_3]
[EN] I have to take care of my daughter.
[PAUSE_5]
[EN] I have to take care of my daughter.
```

The app will:

- Read `[EN]` text with the selected English voice
- Read `[ES]` text with the selected Spanish voice
- Insert timed silent MP3 segments for supported `[PAUSE_X]` tags
- Skip the tags so they are not spoken out loud

If your PDF has no `[EN]` or `[ES]` tags, the app reads all text with the selected English voice.

Unsupported pause tags, such as `[PAUSE_4]`, are ignored and shown as a friendly warning after conversion.

## Shadowing Mode

Enable **Shadowing Mode** in the app to automatically repeat each English phrase.
After every `[EN]` speech segment, EchoLearn inserts a short pause and then plays
the same English phrase again. This helps with pronunciation practice by giving
you a listen-and-repeat pattern without adding any new tags to your PDF.

Shadowing only applies to English text. Spanish text and explicit pause tags keep
their normal behavior.

## Idioms Mode

Enable **Idioms Mode** to automatically repeat each English phrase after its
Spanish translation. For every consecutive `[EN]` and `[ES]` pair, EchoLearn
plays the audio in this order:

```text
English
2 second pause
Spanish
2 second pause
English
```

Example:

```text
[EN] To take care.
[ES] Cuidar.
```

With Idioms Mode enabled, EchoLearn reads:

```text
To take care.
2 second pause
Cuidar.
2 second pause
To take care.
```

**Learning Pauses** are enabled by default to insert automatic practice gaps
inside each Idioms Mode sequence. The pause selector supports 1, 2, 3, or 5
seconds, and the default is 2 seconds.

Learning Pauses only apply when Idioms Mode is enabled. English-only and
Spanish-only segments keep their normal behavior. Idioms Mode and Shadowing Mode
are independent, so either one or both can be enabled.

## Voice Preview

The Preview Voice button allows users to listen to a short sample using the
currently selected English and Spanish voices before generating a full audiobook.

## Saved Settings

EchoLearn remembers your last selected voices, learning modes, folders, speech
rate, and volume. On macOS, settings are saved automatically at
`~/Library/Application Support/EchoLearn/echolearn_settings.json` when you
change options, choose files, or close the app.

## Voice Options

English voices:

- `en-US-JennyNeural`
- `en-US-GuyNeural`
- `en-US-AriaNeural`

Spanish voices:

- `es-CO-SalomeNeural`
- `es-CO-GonzaloNeural`
- `es-MX-DaliaNeural`
- `es-MX-JorgeNeural`
- `es-ES-ElviraNeural`
- `es-ES-AlvaroNeural`

## Notes

- The app works best with PDFs that contain selectable text.
- Scanned or image-only PDFs usually do not contain extractable text. Those files require OCR before conversion.
- Speech generation uses `edge-tts`, so an internet connection is required when creating the MP3.
- FFmpeg is required for real timed pauses. On macOS, install it with `brew install ffmpeg`.

## Troubleshooting

- **Invalid PDF:** Make sure the selected file is a real PDF and is not corrupted.
- **Empty PDF:** Choose a PDF with at least one page.
- **No extractable text:** Use an OCR tool first, then try the OCR-processed PDF.
- **No MP3 created:** Check your internet connection, try saving to a folder where you have write permission, or try a shorter PDF first.
- **FFmpeg missing:** Install FFmpeg so the app can generate real pauses.
- **pyaudiop or pyaudioop error:** Reinstall dependencies with the updated `requirements.txt`; the current app does not use the package that caused this error.

---

# Version History

## v1.3.0 - June 2026

UX refresh with modern dark cards, toggle switches, clickable PDF selection, animated
progress with percentage and task text, and post-conversion Open Audio/Open
Folder actions.

## v1.0.0 - June 2026

Initial public release.

### Features
- PDF to MP3 conversion
- Edge TTS integration
- English and Spanish voice support
- Automatic language switching using [EN] and [ES]
- Real pause generation using FFmpeg
- Adjustable speech rate and volume
- Desktop GUI built with Tkinter

---

# Roadmap

## v1.1.0
- Emotional speaking styles
- Voice preview button
- Improved narration quality

## v1.2.0
- Chapter export
- Chapter navigation

## v2.0.0
- Windows installer
- macOS installer
- Automatic updates
