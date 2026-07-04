"""Vocabulary learning: watches what you dictate and, once an uncommon term
recurs, feeds it to the ASR model as a transcription hint — so Speakr gets
better at *your* words over time. Everything stays in learned_words.json on
this machine."""

import json
import logging
import re
import threading

log = logging.getLogger("speakr.learning")

# Frequent English words we never treat as personal vocabulary.
COMMON_WORDS = frozenset("""
the be to of and a in that have i it for not on with he as you do at this but
his by from they we say her she or an will my one all would there their what
so up out if about who get which go me when make can like time no just him
know take people into year your good some could them see other than then now
look only come its over think also back after use two how our work first well
way even new want because any these give day most us is are was were been has
had did does doing said says got very really actually maybe okay ok yes no
please thanks thank sorry hello hey guys today tomorrow yesterday morning
night monday tuesday wednesday thursday friday saturday sunday january
february march april may june july august september october november december
meeting email message call note list item point number things stuff going
gonna want need let lets don didn won isn aren
""".split())

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'’\-]{2,}")


class VocabLearner:
    def __init__(self, config, path):
        self.config = config
        self.path = path
        self._lock = threading.Lock()
        self._entries: dict[str, dict] = {}
        if path.exists():
            try:
                self._entries = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("Could not read %s: %s", path, exc)

    def _enabled(self) -> bool:
        return bool(self.config.get("learning", "enabled", default=True))

    def observe(self, text: str):
        """Count proper-noun-ish / technical tokens from a finished dictation."""
        if not self._enabled() or not text:
            return
        learned = 0
        with self._lock:
            for token, sentence_start in self._candidates(text):
                if sentence_start:
                    continue  # capitalization there is grammar, not identity
                lower = token.lower()
                if lower in COMMON_WORDS:
                    continue
                looks_notable = (
                    token[0].isupper()
                    or any(ch.isdigit() for ch in token)
                    or "-" in token
                    or any(ch.isupper() for ch in token[1:])  # CamelCase / acronyms
                )
                if not looks_notable:
                    continue
                entry = self._entries.setdefault(lower, {"count": 0, "form": token})
                entry["count"] += 1
                entry["form"] = token  # keep the most recent casing
                learned += 1
            if learned:
                self._save()

    @staticmethod
    def _candidates(text: str):
        for match in TOKEN_RE.finditer(text):
            j = match.start() - 1
            while j >= 0 and text[j] in " \t\"'“”‘’([-":
                j -= 1
            sentence_start = j < 0 or text[j] in ".!?\n:;"
            yield match.group(0), sentence_start

    def hints(self, exclude=()) -> list[str]:
        """Learned words worth biasing the transcriber with."""
        if not self._enabled():
            return []
        min_n = self.config.get("learning", "min_occurrences", default=3)
        cap = self.config.get("learning", "max_hints", default=40)
        excluded = {word.lower() for word in exclude}
        with self._lock:
            ranked = sorted(self._entries.items(), key=lambda kv: -kv[1]["count"])
            return [
                entry["form"]
                for lower, entry in ranked
                if entry["count"] >= min_n and lower not in excluded
            ][:cap]

    def _save(self):
        try:
            self.path.write_text(
                json.dumps(self._entries, indent=1, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as exc:
            log.warning("Could not save %s: %s", self.path, exc)
