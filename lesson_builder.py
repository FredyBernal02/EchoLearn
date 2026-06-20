"""Deterministic foundation for future EchoLesson Builder logic."""

from __future__ import annotations

import re


DIALOGUE_SPEAKER_PATTERN = re.compile(
    r"^\s*(speaker[\s_-]*\d+|[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)\s*:",
    re.IGNORECASE,
)


class LessonBuilder:
    """Generate first-draft EchoLearn lesson structure without AI."""

    def generate_structure(self, pdf_text: str) -> str:
        """Return basic EchoLearn Markup generated from extracted PDF text."""

        lines = [line.strip() for line in pdf_text.splitlines() if line.strip()]
        if not lines:
            return ""

        sections: list[tuple[str, str]] = [("TITLE", lines[0])]
        for line in lines[1:]:
            sections.append((self._classify_line(line), line))

        return self._format_sections(sections)

    def _classify_line(self, line: str) -> str:
        """Classify one source line using deterministic v1 rules."""

        if self._looks_like_dialogue(line):
            return "DIALOG"
        if line.rstrip().endswith("?"):
            return "PRACTICE"
        if len(line) < 80:
            return "FLOW"
        return "FLOW"

    @staticmethod
    def _looks_like_dialogue(line: str) -> bool:
        """Return True when a line has simple dialogue indicators."""

        stripped = line.strip()
        return (
            "*" in stripped
            or ":" in stripped
            or bool(DIALOGUE_SPEAKER_PATTERN.match(stripped))
        )

    @staticmethod
    def _format_sections(sections: list[tuple[str, str]]) -> str:
        """Group consecutive sections with the same tag into readable markup."""

        output: list[str] = []
        current_tag = ""
        current_lines: list[str] = []

        def flush() -> None:
            if current_tag and current_lines:
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
