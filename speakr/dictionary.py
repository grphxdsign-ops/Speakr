"""Personal dictionary: vocabulary hints for the ASR model plus hard
text replacements.

File format (dictionary.txt), one entry per line:
    Speakr                  -> vocabulary hint (biases transcription)
    jira => Jira            -> replacement (applied after transcription)
    # comment lines and blanks are ignored
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
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
        self._lock = threading.RLock()
        self.hints: list[str] = []
        self.replacements: list[tuple[re.Pattern, str]] = []
        self.load()

    def load(self):
        with self._lock:
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

    def entries(self) -> list[dict]:
        """Structured manual entries with content-bound confirmation IDs."""
        with self._lock:
            if not self.path.exists():
                return []
            out = []
            for index, raw in enumerate(self.path.read_text(encoding="utf-8-sig").splitlines()):
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=>" in line:
                    heard, _, intended = (part.strip() for part in line.partition("=>"))
                    if heard and intended:
                        out.append({
                            "id": self._entry_id(index, raw), "kind": "replacement",
                            "heard": heard, "intended": intended,
                            "label": f"{heard} → {intended}",
                        })
                else:
                    out.append({
                        "id": self._entry_id(index, raw),
                        "kind": "word",
                        "word": line,
                        "label": line,
                    })
            return out

    @staticmethod
    def _line_digest(raw: str) -> str:
        return hashlib.blake2s(raw.encode("utf-8"), digest_size=8).hexdigest()

    @classmethod
    def _entry_id(cls, index: int, raw: str) -> str:
        # The digest prevents a confirmation dialog created from an old UI
        # snapshot from deleting whichever unrelated line later occupies the
        # same index after an expert edits dictionary.txt directly.
        return f"{index}:{cls._line_digest(raw)}"

    def _write_lines(self, lines: list[str]):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        # Do not normalize the user's file while making a UI edit.  In
        # particular, comments, unknown lines, ordering, and intentional
        # blank lines are part of the expert escape hatch and must survive.
        # splitlines() represents a trailing blank as a final empty element.
        # Add the file terminator independently so that empty element remains
        # an actual blank line after a round trip.
        payload = "\n".join(lines)
        if lines:
            payload += "\n"
        try:
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, self.path)
        except Exception:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise

    @staticmethod
    def _clean_value(value: str) -> str:
        return " ".join(str(value).replace("\r", " ").replace("\n", " ").split()).strip()

    def add_hint(self, word: str):
        word = self._clean_value(word)
        if not word or word.startswith("#") or "=>" in word:
            raise ValueError("Enter one word or name without '=>'.")
        with self._lock:
            lines = self.path.read_text(encoding="utf-8-sig").splitlines() if self.path.exists() else []
            if any(raw.strip().casefold() == word.casefold() for raw in lines):
                return
            lines.append(word)
            self._write_lines(lines)
            self.load()

    def add_replacement(self, heard: str, intended: str):
        heard, intended = self._clean_value(heard), self._clean_value(intended)
        if not heard or not intended or "=>" in heard or "=>" in intended:
            raise ValueError("Enter both the heard and intended text.")
        with self._lock:
            lines = self.path.read_text(encoding="utf-8-sig").splitlines() if self.path.exists() else []
            rendered = f"{heard} => {intended}"
            if any(raw.strip().casefold() == rendered.casefold() for raw in lines):
                return
            lines.append(rendered)
            self._write_lines(lines)
            self.load()

    def remove_entry(self, entry_id: str):
        with self._lock:
            lines = self.path.read_text(encoding="utf-8-sig").splitlines()
            try:
                raw_index, separator, expected_digest = str(entry_id).partition(":")
                if not separator or not expected_digest:
                    raise ValueError
                original_index = int(raw_index)
            except ValueError:
                raise ValueError("That dictionary entry no longer exists.")

            candidates = [
                index
                for index, raw in enumerate(lines)
                if self._line_digest(raw) == expected_digest
            ]
            if original_index in candidates:
                index = original_index
            elif len(candidates) == 1:
                # Comments or other entries may have been inserted above the
                # confirmed entry. The content identity is still unambiguous.
                index = candidates[0]
            else:
                raise ValueError("That dictionary entry changed. Refresh and try again.")

            line = lines[index].strip()
            if not line or line.startswith("#"):
                raise ValueError("Only dictionary entries can be removed.")
            del lines[index]
            self._write_lines(lines)
            self.load()

    def initial_prompt(self) -> str | None:
        """Vocabulary bias passed to whisper as the initial prompt."""
        if not self.hints:
            return None
        return "Glossary: " + ", ".join(self.hints[:80]) + "."

    def apply(self, text: str) -> str:
        with self._lock:
            replacements = list(self.replacements)
        for pattern, replacement in replacements:
            text = pattern.sub(replacement, text)
        return text
