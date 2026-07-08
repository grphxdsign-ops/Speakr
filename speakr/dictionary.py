"""Personal dictionary: vocabulary hints for the ASR model plus hard
text replacements.

File format (dictionary.txt), one entry per line:
    Speakr                  -> vocabulary hint (biases transcription)
    jira => Jira            -> replacement (applied after transcription)
    # comment lines and blanks are ignored
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger("speakr.dictionary")

STARTER = """\
# Speakr personal dictionary.
# One entry per line:
#   SomeWord            biases transcription toward this spelling
#   wrong => right      replaces text after transcription (case-insensitive)
Speakr
"""


class Dictionary:
    def __init__(self, path: Path):
        self.path = path
        self.hints: list[str] = []
        self.replacements: list[tuple[re.Pattern, str]] = []
        self.load()

    def load(self):
        if not self.path.exists():
            self.path.write_text(STARTER, encoding="utf-8")
        self.hints = []
        self.replacements = []
        for raw in self.path.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=>" in line:
                wrong, _, right = (part.strip() for part in line.partition("=>"))
                if wrong and right:
                    pattern = re.compile(rf"\b{re.escape(wrong)}\b", re.IGNORECASE)
                    self.replacements.append((pattern, right))
                    self.hints.append(right)
            else:
                self.hints.append(line)
        log.info("Dictionary loaded: %d hints, %d replacements", len(self.hints), len(self.replacements))

    def initial_prompt(self) -> str | None:
        """Vocabulary bias passed to whisper as the initial prompt."""
        if not self.hints:
            return None
        return "Glossary: " + ", ".join(self.hints[:80]) + "."

    def apply(self, text: str) -> str:
        for pattern, replacement in self.replacements:
            text = pattern.sub(replacement, text)
        return text
