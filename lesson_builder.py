"""Deterministic EchoLesson structure generation.

This module intentionally stays simple. It creates a reviewable first draft of
EchoLearn Markup without AI, cloud services, or hidden dependencies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


DIALOGUE_SPEAKER_PATTERN = re.compile(
    r"^\s*(speaker[\s_-]*\d+|[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)\s*:",
    re.IGNORECASE,
)
STRUCTURAL_TAG_PATTERN = re.compile(
    r"^\s*\[(TITLE|FLOW|EXPLANATION|DIALOG|PRACTICE|REVIEW|SPEAKER_1|SPEAKER_2)\]\s*$",
    re.IGNORECASE,
)
REVIEW_KEYWORDS = (
    "summary",
    "review",
    "in conclusion",
    "to summarize",
    "today we learned",
    "today we practiced",
    "lets review",
    "let's review",
)
REVIEW_KEYWORDS_V2 = (
    "review",
    "summary",
    "recap",
    "key takeaways",
    "what we learned",
    "in this lesson",
)
EXPLANATION_KEYWORDS = (
    "today we will learn",
    "in this lesson",
    "this lesson covers",
    "the objective is",
    "objective:",
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
CLOSING_PHRASES = (
    "goodbye",
    "see you later",
    "see you soon",
    "thats all for today",
    "that's all for today",
    "that is all for today",
    "end of lesson",
    "great job",
    "well done",
)
NON_DIALOGUE_LABELS = (
    "objective",
    "summary",
    "review",
    "recap",
    "key takeaways",
)


@dataclass(frozen=True)
class LessonAnalysis:
    """Small quality summary for deterministic structure generation."""

    title_count: int = 0
    explanation_count: int = 0
    flow_count: int = 0
    dialogue_count: int = 0
    practice_count: int = 0
    review_count: int = 0

    def format(self) -> str:
        """Return a readable lesson analysis summary."""

        return (
            "Lesson Analysis:\n"
            f"Title: {self.title_count}\n"
            f"Explanation: {self.explanation_count}\n"
            f"Flow Sections: {self.flow_count}\n"
            f"Dialogues: {self.dialogue_count}\n"
            f"Practice Questions: {self.practice_count}\n"
            f"Review Sections: {self.review_count}"
        )


class LessonBuilder:
    """Generate first-draft EchoLearn lesson structure without AI."""

    def __init__(self) -> None:
        self.last_analysis = LessonAnalysis()

    def generate_structure(self, pdf_text: str) -> str:
        """Return v3 EchoLearn Markup generated from extracted PDF text."""

        return self.generate_structure_v3(pdf_text)

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

    def generate_structure_v3(self, pdf_text: str) -> str:
        """Return better v3 structure using deterministic lesson rules."""

        lines = [line.strip() for line in pdf_text.splitlines() if line.strip()]
        if not lines:
            self.last_analysis = LessonAnalysis()
            return ""

        title = self._find_title(lines)
        sections: list[tuple[str, str]] = [("TITLE", title)]

        body_lines = self._body_lines_without_title(lines, title)
        for index, line in enumerate(body_lines):
            sections.append(
                (
                    self._classify_line_v3(index, len(body_lines), line),
                    self._clean_dialogue_line(line),
                )
            )

        self.last_analysis = self._analyze_sections(sections)
        return self._format_sections(sections, add_speaker_tags=True)

    def _body_lines_without_title(self, lines: list[str], title: str) -> list[str]:
        """Return source lines after removing the first title occurrence."""

        body_lines: list[str] = []
        title_used = False
        for line in lines:
            if not title_used and line == title:
                title_used = True
                continue
            body_lines.append(line)
        return body_lines

    def generate_structure_with_analysis(
        self,
        pdf_text: str,
    ) -> tuple[str, LessonAnalysis]:
        """Return v3 markup and its lesson analysis summary."""

        markup = self.generate_structure_v3(pdf_text)
        return markup, self.last_analysis

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

        if self._looks_like_review_v2(line):
            return "REVIEW"
        if self._looks_like_dialogue(line):
            return "DIALOG"
        if self._looks_like_practice(line):
            return "PRACTICE"
        if self._looks_like_explanation(line):
            return "EXPLANATION"
        return "FLOW"

    def _classify_line_v3(self, index: int, total_lines: int, line: str) -> str:
        """Classify one source line using deterministic v3 lesson rules."""

        if self._looks_like_review(line) or (
            self._is_near_end(index, total_lines)
            and self._looks_like_closing(line)
        ):
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
        label = stripped.split(":", 1)[0].strip().lower() if ":" in stripped else ""
        if label in NON_DIALOGUE_LABELS:
            return False
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

        normalized = LessonBuilder._normalize_rule_text(line)
        if normalized in {"summary", "review"}:
            return True
        if normalized.startswith(("summary ", "review ")):
            return True
        return any(
            keyword in normalized
            for keyword in REVIEW_KEYWORDS
            if keyword not in {"summary", "review"}
        )

    @staticmethod
    def _looks_like_closing(line: str) -> bool:
        """Return True for closing phrases used at the end of lessons."""

        normalized = LessonBuilder._normalize_rule_text(line)
        return any(phrase in normalized for phrase in CLOSING_PHRASES)

    @staticmethod
    def _is_near_end(index: int, total_lines: int) -> bool:
        """Return True when a body line appears in the ending area."""

        if total_lines <= 0:
            return False
        return index >= min(max(total_lines - 4, 0), int(total_lines * 0.75))

    @staticmethod
    def _normalize_rule_text(line: str) -> str:
        """Normalize punctuation enough for simple keyword rules."""

        normalized = line.strip().lower().replace("’", "'")
        normalized = normalized.rstrip(".!?:;")
        return normalized

    @staticmethod
    def _looks_like_review_v2(line: str) -> bool:
        """Return True for review-like lines using the original v2 keywords."""

        normalized = line.strip().lower()
        return any(keyword in normalized for keyword in REVIEW_KEYWORDS_V2)

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

            spoken_line = LessonBuilder._strip_dialogue_speaker_name(line)
            if not spoken_line:
                continue

            formatted_lines.append(f"[{speaker_tag}]")
            formatted_lines.append(spoken_line)

        return "\n".join(formatted_lines)

    @staticmethod
    def _strip_dialogue_speaker_name(line: str) -> str:
        """Remove speaker labels such as 'Michael:' from spoken dialogue."""

        stripped = line.strip()
        speaker_match = DIALOGUE_SPEAKER_PATTERN.match(stripped)
        if speaker_match:
            return stripped[speaker_match.end():].strip()
        return stripped

    @staticmethod
    def _analyze_sections(sections: list[tuple[str, str]]) -> LessonAnalysis:
        """Count generated lesson parts for a simple quality summary."""

        return LessonAnalysis(
            title_count=sum(1 for tag, _line in sections if tag == "TITLE"),
            explanation_count=LessonBuilder._count_tag_blocks(sections, "EXPLANATION"),
            flow_count=LessonBuilder._count_tag_blocks(sections, "FLOW"),
            dialogue_count=LessonBuilder._count_tag_blocks(sections, "DIALOG"),
            practice_count=sum(1 for tag, _line in sections if tag == "PRACTICE"),
            review_count=LessonBuilder._count_tag_blocks(sections, "REVIEW"),
        )

    @staticmethod
    def _count_tag_blocks(sections: list[tuple[str, str]], target_tag: str) -> int:
        """Count consecutive runs for a generated section tag."""

        count = 0
        previous_tag = ""
        for tag, _line in sections:
            if tag == target_tag and previous_tag != target_tag:
                count += 1
            previous_tag = tag
        return count
