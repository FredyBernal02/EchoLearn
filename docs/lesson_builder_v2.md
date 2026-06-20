# EchoLesson Structure Generator v2

EchoLesson Structure Generator v2 creates editable EchoLearn Markup from
extracted PDF text using simple deterministic rules. It does not use AI.

## Current Flow

```text
PDF
↓
Generate Lesson Structure
↓
Editable EchoLearn Markup Preview
↓
Generate Learning Audio
```

## Detection Rules

1. The first non-empty line becomes `[TITLE]`.
2. Review-like lines become `[REVIEW]`.
   Examples include lines containing words such as `review`, `summary`,
   `recap`, `key takeaways`, or `what we learned`.
3. Dialogue-like lines become `[DIALOG]`.
   Examples include simple speaker labels like `Michael:`, `Speaker 1:`, or
   bullet-style conversation lines.
4. Questions and learner prompts become `[PRACTICE]`.
   Examples include lines ending with `?` or containing words such as
   `practice`, `try`, `repeat`, or `answer`.
5. Explanation-like lines become `[EXPLANATION]`.
   Examples include long lines or lines containing phrases such as `because`,
   `means`, `for example`, or `in other words`.
6. All remaining content becomes `[FLOW]`.

Consecutive lines with the same tag are grouped together to keep the generated
markup readable.

## Editable Preview

After generation, the Lesson Structure Preview can be edited manually before
audio generation. In EchoLesson Mode, EchoLearn parses the edited preview
markup into audio segments.

EchoLesson audio generation interprets tags before text-to-speech:

- `[SPEAKER_1]` uses the selected English voice.
- `[SPEAKER_2]` uses the selected Spanish voice.
- `[PRACTICE]` adds a learning pause after each practice line.
- `[PAUSE_1]`, `[PAUSE_2]`, `[PAUSE_3]`, `[PAUSE_5]`, `[PAUSE_8]`, and
  `[PAUSE_10]` create real silence.
- Markup tags are not spoken aloud.

## Known Limitations

- The generator does not understand meaning like an AI model would.
- Bullet lists can still be mistaken for dialogue.
- Some labels with `:` can be mistaken for speaker lines.
- Speaker assignment is not automatic yet.
- Review, practice, and explanation detection are keyword-based.
- The generated markup is a first draft for review, not a finished lesson.

## Future AI Replacement

Future versions can replace these deterministic rules with an AI Lesson Builder
that understands PDF context, detects speakers more accurately, inserts better
pauses, and creates richer EchoLearn Markup.
