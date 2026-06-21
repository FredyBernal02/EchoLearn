# EchoLesson Structure Generator v3

EchoLesson Structure Generator v3 creates editable EchoLearn Markup from
extracted PDF text using deterministic rules only. It does not use AI, cloud
services, accounts, or mobile-specific features.

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
2. Educational introduction lines become `[EXPLANATION]`.
   Examples include `Today we will learn`, `In this lesson`,
   `This lesson covers`, and `The objective is`.
3. Speaker-label dialogue becomes `[DIALOG]` with alternating
   `[SPEAKER_1]` and `[SPEAKER_2]` tags. Speaker names such as `Michael:` and
   `Ana:` are removed from the spoken content.
4. Questions and learner prompts become `[PRACTICE]`.
5. Summary and review lines become `[REVIEW]`.
   Examples include `Summary:`, `Review:`, `In conclusion`,
   `To summarize`, `Today we learned`, `Today we practiced`, and
   `Let's review`.
6. Closing lines near the end of a lesson become `[REVIEW]`.
   Examples include `Goodbye`, `See you later`, `See you soon`,
   `That's all for today`, `End of lesson`, `Great job`, and `Well done`.
7. Consecutive lines with the same tag are grouped together. This keeps normal
   lesson text in a single `[FLOW]` block when possible.

## Lesson Analysis

After generation, EchoLearn creates a simple lesson analysis summary:

```text
Lesson Analysis:
Title: 1
Explanation: 1
Flow Sections: 3
Dialogues: 1
Practice Questions: 3
Review Sections: 1
```

The summary is intended to help users understand whether the generated draft has
the basic parts of a useful lesson before they edit the preview and generate
audio.

## Known Limitations

- The generator is deterministic and does not understand meaning like an AI
  model would.
- Speaker assignment is limited to two speaker tags.
- Dialogue, review, practice, and explanation detection are still
  keyword-pattern based.
- The generated markup is a first draft for review, not a finished lesson.
