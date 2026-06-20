# EchoLesson Structure Generator v1

EchoLesson Structure Generator v1 creates a first-draft EchoLearn Markup
structure from extracted PDF text using deterministic rules. It does not use AI.

## Current Structure Generation Rules

1. The first non-empty line becomes `[TITLE]`.
2. Lines with dialogue indicators become `[DIALOG]`.
   Current indicators include `*`, `:`, and simple speaker-name patterns such
   as `Michael:` or `Speaker 1:`.
3. Lines ending with `?` become `[PRACTICE]`.
4. Lines shorter than 80 characters become `[FLOW]`.
5. All remaining content becomes `[FLOW]`.

Consecutive lines with the same tag are grouped together in the generated
preview.

## Known Limitations

- The generator does not understand meaning or lesson intent.
- Bullet lists that use `*` may be classified as dialogue.
- Any line containing `:` may be classified as dialogue, even if it is a heading
  or label.
- Long explanations are currently still treated as `[FLOW]`.
- Speaker detection is simple and may miss dialogue without clear indicators.
- The generated structure is a first draft for review, not final lesson markup.

## Future AI Replacement

Future versions of EchoLearn will replace or augment these deterministic rules
with an AI Lesson Builder that can detect lesson structure more accurately,
including titles, explanations, dialogues, speakers, practice sections, reviews,
and pauses.
