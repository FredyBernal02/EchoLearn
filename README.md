# EchoLearn

Convert PDFs into natural-sounding audiobooks using Microsoft Edge TTS voices, bilingual narration, and real FFmpeg-generated pauses.

A cross-platform desktop app that converts selectable-text PDF files into MP3 audiobooks.

The app can automatically detect English and Spanish in normal selectable-text
PDFs. It also supports simple script tags inside the PDF text for advanced
voice control and timed pauses.

## Features

- Tkinter graphical interface
- PDF text extraction with `pypdf`
- Text-to-speech MP3 generation with `edge-tts`
- Real timed pause generation with FFmpeg
- English and Spanish voice selectors
- Automatic English/Spanish detection for untagged PDF text
- Default language setting for uncertain untagged text
- Voice Preview for selected voices and speech settings
- Speech rate and volume controls
- Auto Learning Pauses for normal PDFs without pause tags
- Auto pause segmentation by sentence or paragraph/idea block
- Modern dark interface with toggle switches
- Official EchoLearn logo in the app header
- Clickable PDF selection area with Browse PDF fallback
- Detailed progress with page, segment, and percentage updates
- Open Audio and Reveal MP3 actions after conversion
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
5. Leave **Auto-detect language** on for normal PDFs, or choose the default
   language for untagged text.
6. Optionally enable **Auto Learning Pauses**, choose an auto pause duration,
   and choose whether pauses are added by **Paragraph** or **Sentence**.
7. Adjust speech rate and volume.
8. Click **Convert to MP3**.
9. Follow the progress percentage, current page, and current segment updates.
10. Use **Open Audio** or **Reveal MP3** after conversion, or enable **Open audio automatically when finished**.

## Interface

EchoLearn uses a dark, card-based desktop interface with modern toggle switches
for optional audio behavior, larger controls, and a progress area that shows both the
current task and percentage completed.

The PDF section includes a clickable selection area and a **Browse PDF** button.
Both open the same file picker and load the selected PDF.

Speech rate uses simple dropdown options: **Very Slow**, **Slow**, **Normal**,
**Fast**, and **Very Fast**. Volume uses **Very Low**, **Low**, **Normal**,
**High**, and **Very High**.

The Voices section includes **Auto-detect language** and **Default language for
untagged text**. Auto-detect is on by default. When EchoLearn cannot confidently
detect a segment, it uses the selected default language, which is English by
default.

Auto Learning Pauses can be inserted by **Paragraph** or **Sentence**.
**Paragraph** is the default and treats consecutive instructional sentences as
one idea block, so EchoLearn pauses after the explanation instead of between
each sentence. **Sentence** inserts pauses after each complete sentence. Titles,
short standalone prompts, short English dialogue lines, and manual pause tags
remain separate boundaries.

EchoLearn also detects simple practice sections automatically without AI. It
starts in Flow Mode, reading titles, introductions, explanations, and full
dialogues naturally without long learning pauses. When it sees practice cues
such as **Repite**, **Escucha y repite**, **Intenta responder**, **Try to
answer**, or **Listen and repeat**, it switches to Practice Mode and applies
Auto Learning Pauses after practice segments. Transition phrases such as
**Muy bien**, **Excelente**, **Now listen to the full conversation**, and
**That is all for today** return the lesson to Flow Mode.

## Workflow

EchoLearn stays focused on four steps:

1. Select a PDF.
2. Configure voices, language detection, and optional auto pauses.
3. Convert to MP3.
4. Open Audio or Reveal MP3.

## Writing PDF Scripts

EchoLearn works with normal selectable-text PDFs without language tags. For
untagged text, it checks each paragraph or sentence for Spanish characters,
common Spanish words, and common English words, then chooses the matching voice.
If detection is uncertain, it uses **Default language for untagged text**.

For normal lesson PDFs, EchoLearn first cleans extracted text by merging wrapped
PDF lines into final speech segments. With Auto Learning Pauses set to
**Paragraph**, related instructional sentences are grouped into one idea block
and receive one pause at the end. With **Sentence**, each complete sentence can
receive its own pause.

Manual pause tags such as `[PAUSE_3]` still override automatic practice pauses,
so EchoLearn does not add a duplicate Auto Learning Pause immediately before a
manual pause.

Tags are still supported for advanced control. Add tags directly in your PDF
text when you want to force a specific voice or add timed pauses. `[EN]` and
`[ES]` always override automatic detection.

## EchoLearn Markup Language

Structured content can use EchoLearn Markup Language tags like `[TITLE]`,
`[FLOW]`, `[DIALOG]`, and `[PRACTICE]` to give EchoLearn more precise control
over lesson structure before audio generation. Existing `[EN]`, `[ES]`, and
`[PAUSE_X]` tags remain supported for voice selection and exact timed pauses.
Future markup support will include multi-speaker dialogues with tags like
`[SPEAKER_1]` and `[SPEAKER_2]` so conversations can use different assigned
voices.

See `docs/echolearn_markup_language_v1.md` for the v1 markup documentation.

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

If **Auto-detect language** is off, untagged text is read with the selected
default language instead. If many segments need that fallback while auto-detect
is on, EchoLearn shows a friendly warning after conversion.

Unsupported pause tags, such as `[PAUSE_4]`, are ignored and shown as a friendly
warning after conversion.

## Auto Learning Pauses

Enable **Auto Learning Pauses** to add thinking time between normal untagged PDF
segments without adding `[PAUSE_X]` tags to the document. EchoLearn detects each
complete sentence, chooses the English or Spanish voice, then inserts the
selected pause duration after that sentence when another speech segment follows.
Wrapped PDF lines that belong to the same sentence are merged before detection.

The **Auto pause duration** selector supports 1, 2, 3, 5, and 8 seconds. The
default is 3 seconds. Manual pause tags still work and take priority, so a
`[PAUSE_5]` tag produces exactly a 5 second pause without an extra automatic
pause next to it.

## Voice Preview

The Preview Voice button allows users to listen to a short sample using the
currently selected English and Spanish voices before generating a full audiobook.

## Saved Settings

EchoLearn remembers your last selected voices, language detection options,
auto pause settings, folders, speech rate, and volume. On macOS,
settings are saved automatically at
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
- Automatic language detection for normal PDFs
- Auto Learning Pauses for normal PDFs without pause tags
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
