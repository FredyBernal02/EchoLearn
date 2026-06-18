# EchoLearn Markup Language v1

EchoLearn Markup Language is a simple tag system used to structure content before
converting it to audio.

## Purpose

EchoLearn Markup Language gives EchoLearn clear instructions about how different
parts of a lesson should be treated by the audio engine. It separates titles,
natural reading flow, explanations, dialogues, practice lines, review items,
language selection, and exact pauses.

## Why It Exists

Normal PDFs are messy. They may contain titles, explanations, dialogues,
practice lines, and exercises.

EchoLearn should not try to guess everything. Instead, AI or advanced content
tools can convert messy PDFs into structured EchoLearn markup before audio
generation begins.

## Tags

### [TITLE]

Used for lesson titles or section titles.

Behavior:

- Read normally.
- No long learning pause after it.

### [FLOW]

Used for introductions, explanations, or narrative content that should be read
naturally.

Behavior:

- Read continuously.
- No long learning pause after every sentence.

### [EXPLANATION]

Used for teaching explanations.

Behavior:

- Read clearly.
- Short natural pause allowed after the block.

### [DIALOG]

Used for conversations.

Behavior:

- Read naturally as conversation.
- No long learning pause between every dialogue line unless manually requested.

### [PRACTICE]

Used for sentences the learner should repeat, answer, or actively practice.

Behavior:

- Insert the selected Auto Learning Pause after each practice line.

### [REVIEW]

Used for review sections.

Behavior:

- Insert learning pauses after each item.

### [EN]

Explicitly marks English text.

Behavior:

- Use English voice.

### [ES]

Explicitly marks Spanish text.

Behavior:

- Use Spanish voice.

### [PAUSE_1], [PAUSE_2], [PAUSE_3], [PAUSE_5], [PAUSE_8], [PAUSE_10]

Manual exact pauses.

Behavior:

- Insert exact silence.

## Conversation Speakers

### [SPEAKER_1]

Used to identify the first speaker in a dialogue.

Behavior:

- Uses the voice assigned to Speaker 1.
- Can be male or female.
- Works with any language.

### [SPEAKER_2]

Used to identify the second speaker in a dialogue.

Behavior:

- Uses the voice assigned to Speaker 2.
- Can be male or female.
- Works with any language.

### Future Engine Behavior

The EchoLearn engine will allow assigning different voices to each speaker.

Example:

Speaker 1:

- `en-US-JennyNeural`
- `es-CO-SalomeNeural`

Speaker 2:

- `en-US-GuyNeural`
- `es-MX-JorgeNeural`

When processing dialogue blocks, EchoLearn should switch voices automatically
according to the speaker tags.

## Examples

### Example 1: Basic bilingual learning

```text
[TITLE]
Lesson 1 - Greetings

[FLOW]
Hoy vamos a aprender saludos básicos en inglés.

[PRACTICE]
[ES] Disculpe.
[EN] Excuse me.

[PRACTICE]
[ES] ¿Hablas inglés?
[EN] Do you speak English?
```

### Example 2: Dialogue

```text
[DIALOG]
[EN] Excuse me.
[EN] Do you speak English?
[EN] Yes, I speak a little English.
```

### Example 3: Review

```text
[REVIEW]
[ES] Disculpe.
[EN] Excuse me.

[ES] Mucho gusto.
[EN] Nice to meet you.
```

### Example 4: Multi-speaker dialogue

```text
[DIALOG]

[SPEAKER_1]
[EN] Hello John.

[SPEAKER_2]
[EN] Hello Monica. Long time no see.

[SPEAKER_1]
[EN] How have you been?

[SPEAKER_2]
[EN] I have been great.
```

### Example 5: Bilingual multi-speaker dialogue

```text
[DIALOG]

[SPEAKER_1]
[ES] Hola Juan.

[SPEAKER_2]
[ES] Hola Monica. Cuánto tiempo sin verte.

[SPEAKER_1]
[EN] How have you been?

[SPEAKER_2]
[EN] I have been great.
```

## Recommended Rules for AI-Generated EchoLearn Content

- Always use tags.
- Do not rely on EchoLearn guessing the content type.
- Use `[PRACTICE]` only when the learner should pause and respond.
- Use `[FLOW]` for explanations and introductions.
- Use `[DIALOG]` for conversations.
- Use `[SPEAKER_1]` and `[SPEAKER_2]` only inside `[DIALOG]` sections.
- Alternate speakers whenever a conversation occurs.
- Avoid putting long explanations inside dialogue blocks.
- Dialogue should feel natural and conversational.
- Use `[PAUSE_X]` only when exact silence is needed.
- Use punctuation clearly.
- Keep practice items short.
- Future AI Lesson Builder should automatically identify speakers and assign
  speaker tags when converting normal PDFs into EchoLearn Markup.

## Future Note

In a later version, EchoLearn will include an AI Lesson Builder that converts
normal PDFs into this markup automatically.
