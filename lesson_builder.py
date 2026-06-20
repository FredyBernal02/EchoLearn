"""Deterministic EchoLesson structure generation.

This module intentionally stays simple. It creates a reviewable first draft of
EchoLearn Markup without AI, cloud services, or hidden dependencies.
"""

from __future__ import annotations

import re


DIALOGUE_SPEAKER_PATTERN = re.compile(
    r"^\s*(speaker[\s_-]*\d+|[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)\s*:",
    re.IGNORECASE,
)
STRUCTURAL_TAG_PATTERN = re.compile(
    r"^\s*\[(TITLE|FLOW|EXPLANATION|DIALOG|PRACTICE|REVIEW|SPEAKER_1|SPEAKER_2)\]\s*$",
    re.IGNORECASE,
)
REVIEW_KEYWORDS = (
    "review",
    "summary",
    "recap",
    "key takeaways",
    "what we learned",
    "in this lesson",
)
EXPLANATION_KEYWORDS = (
    "because",
    "means",
    "refers to",
    "is used to",
    "for example",
    "in other words",
    "this means",
)
PRACTICE_KEYWORDS = (
    "practice",
    "try",
    "repeat",
    "answer",
    "write",
    "say",
    "fill in",
)


class LessonBuilder:
    """Generate first-draft EchoLearn lesson structure without AI."""

    def generate_structure(self, pdf_text: str) -> str:
        """Return v2 EchoLearn Markup generated from extracted PDF text."""

        return self.generate_structure_v2(pdf_text)

    def generate_structure_v1(self, pdf_text: str) -> str:
        """Return the original simple v1 structure, kept for compatibility."""

        lines = [line.strip() for line in pdf_text.splitlines() if line.strip()]
        if not lines:
            return ""

        sections: list[tuple[str, str]] = [("TITLE", lines[0])]
        for line in lines[1:]:
            sections.append((self._classify_line_v1(line), line))

        return self._format_sections(sections, add_speaker_tags=False)

    def generate_structure_v2(self, pdf_text: str) -> str:
        """Return cleaner v2 structure using deterministic lesson rules."""

        lines = [line.strip() for line in pdf_text.splitlines() if line.strip()]
        if not lines:
            return ""

        title = self._find_title(lines)
        sections: list[tuple[str, str]] = [("TITLE", title)]
        title_used = False

        for line in lines:
            if not title_used and line == title:
                title_used = True
                continue
            sections.append((self._classify_line_v2(line), self._clean_dialogue_line(line)))

        return self._format_sections(sections, add_speaker_tags=True)

    def markup_to_audio_text(self, markup: str) -> str:
        """Remove structure-only tags before sending edited markup to TTS."""

        audio_lines: list[str] = []
        for line in markup.splitlines():
            stripped = line.strip()
            if not stripped:
                audio_lines.append("")
                continue
            if STRUCTURAL_TAG_PATTERN.match(stripped):
                continue
            audio_lines.append(line)
        return "\n".join(audio_lines).strip()

    def _classify_line_v1(self, line: str) -> str:
        """Classify one source line using deterministic v1 rules."""

        if self._looks_like_dialogue(line):
            return "DIALOG"
        if line.rstrip().endswith("?"):
            return "PRACTICE"
        if len(line) < 80:
            return "FLOW"
        return "FLOW"

    def _classify_line_v2(self, line: str) -> str:
        """Classify one source line using small, readable v2 rules."""

        if self._looks_like_review(line):
            return "REVIEW"
        if self._looks_like_dialogue(line):
            return "DIALOG"
        if self._looks_like_practice(line):
            return "PRACTICE"
        if self._looks_like_explanation(line):
            return "EXPLANATION"
        return "FLOW"

    @staticmethod
    def _find_title(lines: list[str]) -> str:
        """Pick the first non-empty line as the lesson title."""

        return lines[0]

    @staticmethod
    def _looks_like_dialogue(line: str) -> bool:
        """Return True when a line has simple dialogue indicators."""

        stripped = line.strip()
        return (
            stripped.startswith(("-", "•", "*"))
            or bool(DIALOGUE_SPEAKER_PATTERN.match(stripped))
            or (
                ":" in stripped
                and len(stripped.split(":", 1)[0].split()) <= 3
            )
        )

    @staticmethod
    def _looks_like_practice(line: str) -> bool:
        """Return True for questions and obvious learner prompts."""

        normalized = line.strip().lower()
        return (
            normalized.endswith("?")
            or any(keyword in normalized for keyword in PRACTICE_KEYWORDS)
        )

    @staticmethod
    def _looks_like_review(line: str) -> bool:
        """Return True for review or summary-like lines."""

        normalized = line.strip().lower()
        return any(keyword in normalized for keyword in REVIEW_KEYWORDS)

    @staticmethod
    def _looks_like_explanation(line: str) -> bool:
        """Return True for lines that read like explanations."""

        normalized = line.strip().lower()
        return (
            len(line) >= 80
            or any(keyword in normalized for keyword in EXPLANATION_KEYWORDS)
        )

    @staticmethod
    def _clean_dialogue_line(line: str) -> str:
        """Remove a leading bullet marker from dialogue-like lines."""

        stripped = line.strip()
        if stripped.startswith(("-", "•", "*")):
            return stripped[1:].strip()
        return line

    def _format_sections(
        self,
        sections: list[tuple[str, str]],
        *,
        add_speaker_tags: bool,
    ) -> str:
        """Group consecutive sections with the same tag into readable markup."""

        output: list[str] = []
        current_tag = ""
        current_lines: list[str] = []

        def flush() -> None:
            if current_tag and current_lines:
                if current_tag == "DIALOG" and add_speaker_tags:
                    output.append(
                        f"[{current_tag}]\n"
                        + self._format_dialogue_lines(current_lines)
                    )
                else:
                    output.append(f"[{current_tag}]\n" + "\n".join(current_lines))

        for tag, line in sections:
            if tag != current_tag:
                flush()
                current_tag = tag
                current_lines = [line]
            else:
                current_lines.append(line)
        flush()

        return "\n\n".join(output)

    @staticmethod
    def _format_dialogue_lines(lines: list[str]) -> str:
        """Add simple alternating speaker tags to generated dialogue."""

        formatted_lines: list[str] = []
        speaker_by_name: dict[str, str] = {}
        next_speaker_number = 1

        for index, line in enumerate(lines):
            speaker_tag = ""
            speaker_match = DIALOGUE_SPEAKER_PATTERN.match(line)
            if speaker_match:
                speaker_name = speaker_match.group(1).strip().lower()
                if speaker_name not in speaker_by_name:
                    speaker_by_name[speaker_name] = (
                        "SPEAKER_1"
                        if next_speaker_number == 1
                        else "SPEAKER_2"
                    )
                    next_speaker_number = 2 if next_speaker_number == 1 else 1
                speaker_tag = speaker_by_name[speaker_name]
            else:
                speaker_tag = "SPEAKER_1" if index % 2 == 0 else "SPEAKER_2"

            formatted_lines.append(f"[{speaker_tag}]")
            formatted_lines.append(line)

        return "\n".join(formatted_lines)
