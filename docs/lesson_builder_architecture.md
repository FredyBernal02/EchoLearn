# EchoLesson Builder Architecture

EchoLesson Builder is the future layer that will transform normal PDFs into
structured EchoLearn Markup Language before lesson-style audio generation.

AI is not implemented yet. The current application still uses the existing
audiobook conversion engine.

## Current Flow

```text
PDF
↓
Audiobook Engine
↓
MP3
```

## Future Flow

```text
PDF
↓
AI Lesson Builder
↓
EchoLearn Markup
↓
EchoLesson Engine
↓
MP3
```

## Future Responsibilities

The EchoLesson Builder will eventually:

- Detect titles
- Detect explanations
- Detect dialogues
- Detect speakers
- Detect practice sections
- Insert pauses
- Generate EchoLearn Markup

## Current Foundation

The current foundation includes:

- An EchoLesson-only Builder section in the UI
- An editable Lesson Structure Preview
- A deterministic Generate Lesson Structure action
- A `LessonBuilder` class in `lesson_builder.py`
- EchoLesson audio generation from the edited preview markup

Audiobook Mode continues to use the original PDF-to-audio path.
