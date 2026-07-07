"""Speakr smoke test — exercises every pipeline stage except live mic/hotkey.

Run:  .venv\\Scripts\\python.exe scripts\\smoke_test.py <path-to-16k-mono-wav>
The wav should contain spoken English; the test checks it transcribes.
"""

import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

passed = []
failed = []


def check(name, fn):
    try:
        fn()
        passed.append(name)
        print(f"  PASS  {name}")
    except Exception as exc:
        failed.append((name, exc))
        print(f"  FAIL  {name}: {exc!r}")


def test_imports():
    import speakr.app  # noqa: F401  (pulls in every module)


def test_formatter_rules():
    from speakr.formatter import rule_based_clean

    assert rule_based_clean("um, hello there, uh, this is a test") == "Hello there, this is a test"
    assert rule_based_clean("okay so umm let's go") == "Okay so let's go"
    assert rule_based_clean("wait , what ?") == "Wait, what?"
    assert rule_based_clean("Hmm. Fine.") == "Fine."
    # Fillers with trailing ellipsis / dashes (how whisper often writes them).
    assert rule_based_clean("Um... let's start over") == "Let's start over"
    assert rule_based_clean("so, uh- I was thinking") == "So, I was thinking"
    # Sentence following a removed filler gets recapitalized.
    assert rule_based_clean("Great. Um, so next steps") == "Great. So next steps"
    # Words *containing* filler substrings must survive.
    assert "umbrella" in rule_based_clean("bring the umbrella")
    assert "ahead" in rule_based_clean("go ahead")
    assert "her" in rule_based_clean("tell her hi")


def test_voice_commands():
    from speakr.formatter import apply_voice_commands

    assert apply_voice_commands("groceries new line milk new line eggs") == "groceries\nmilk\neggs"
    assert (
        apply_voice_commands("todo list bullet point fix bug bullet point ship it")
        == "todo list\n- fix bug\n- ship it"
    )
    assert apply_voice_commands("intro new paragraph body") == "intro\n\nbody"
    # No false trigger inside other words.
    assert apply_voice_commands("the airline industry") == "the airline industry"


def test_vocab_learning():
    from speakr.config import Config
    from speakr.learning import VocabLearner

    path = ROOT / "scripts" / "_learned_test.json"
    if path.exists():
        path.unlink()
    try:
        learner = VocabLearner(Config(), path)
        for _ in range(3):
            learner.observe("ping the Kubernetes cluster about GraphQL and the meeting")
        hints = learner.hints()
        assert "Kubernetes" in hints, hints
        assert "GraphQL" in hints, hints
        assert "meeting" not in [h.lower() for h in hints]  # common word
        # Sentence-initial capitalization alone shouldn't teach a word.
        fresh = VocabLearner(Config(), path.with_suffix(".2.json"))
        for _ in range(3):
            fresh.observe("Tell me more. Tell me again.")
        assert fresh.hints() == [], fresh.hints()
    finally:
        path.unlink(missing_ok=True)
        path.with_suffix(".2.json").unlink(missing_ok=True)


def test_ollama_formatting():
    import requests

    from speakr.config import Config
    from speakr.formatter import Formatter

    cfg = Config()
    try:
        requests.get(cfg.get("formatting", "ollama_url") + "/api/tags", timeout=2)
    except requests.RequestException:
        print("        (ollama not running — skipping LLM checks)")
        return
    formatter = Formatter(cfg)
    ctx = {"exe": "slack.exe", "title": "general - Slack"}

    corrected = formatter.format("Let's meet at 2. Actually, let's do 3.", ctx)
    print(f"        correction: {corrected!r}")
    assert "3" in corrected
    assert "2" not in corrected, f"self-correction not applied: {corrected!r}"

    listed = formatter.format(
        "I need three things from the store. First, apples. Second, bananas. Third, a dozen eggs.",
        ctx,
    )
    print(f"        list: {listed!r}")
    assert listed.count("\n") >= 2, f"expected multi-line list, got: {listed!r}"

    numbered = formatter.format("i need to buy 3 things, an apple, orange, and banana", ctx)
    print(f"        numbered: {numbered!r}")
    assert "1. Apple\n2. Orange\n3. Banana" in numbered, f"numbered list wrong: {numbered!r}"
    assert ":\n\n" in numbered, f"missing blank line after intro: {numbered!r}"

    inline = formatter.format("We grabbed coffee, toast, and eggs before our flight.", ctx)
    print(f"        inline: {inline!r}")
    assert "\n" not in inline, f"list wrongly forced on flowing sentence: {inline!r}"

    chained = formatter.format("call John, no wait Mike, actually just call Dave instead", ctx)
    print(f"        chained correction: {chained!r}")
    assert "dave" in chained.lower(), f"chained correction lost final target: {chained!r}"
    assert "john" not in chained.lower() and "mike" not in chained.lower(), (
        f"chained correction kept a retracted name: {chained!r}"
    )

    # A dictated question must pass through cleaned — never be answered.
    from speakr.formatter import looks_like_answer

    question = formatter.format("Um, what time is the meeting tomorrow?", ctx)
    print(f"        question: {question!r}")
    assert "meeting" in question.lower(), f"question mangled: {question!r}"
    assert not looks_like_answer("Um, what time is the meeting tomorrow?", question), (
        f"model answered the dictation: {question!r}"
    )


def test_dictionary():
    from speakr.dictionary import Dictionary

    path = ROOT / "scripts" / "_dict_test.txt"
    path.write_text("# comment\nSpeakr\njira => Jira\n", encoding="utf-8")
    try:
        d = Dictionary(path)
        assert "Speakr" in d.initial_prompt()
        assert d.apply("filed a JIRA ticket") == "filed a Jira ticket"
    finally:
        path.unlink()


def test_active_app():
    from speakr.context import get_active_app

    ctx = get_active_app()
    assert isinstance(ctx, dict) and "exe" in ctx and "title" in ctx
    print(f"        foreground: {ctx['exe']!r}")


def test_clipboard_roundtrip():
    import pyperclip

    original = pyperclip.paste()
    pyperclip.copy("speakr-smoke-test")
    assert pyperclip.paste() == "speakr-smoke-test"
    pyperclip.copy(original)


def test_config_defaults():
    from speakr.config import Config

    cfg = Config()
    assert cfg.get("hotkey")
    assert cfg.get("formatting", "ollama_url").startswith("http://127.0.0.1")
    assert cfg.get("app_tones", "code.exe") == "literal"
    assert cfg.get("hotkey_exclude_apps") == []


def test_hotkey_exclusion():
    from speakr.app import _is_app_excluded

    excluded = ["LeagueOfLegends.exe", "csgo.exe"]
    assert _is_app_excluded("leagueoflegends.exe", excluded), "case-insensitive match failed"
    assert _is_app_excluded("LeagueOfLegends.exe", excluded)
    assert not _is_app_excluded("notepad.exe", excluded)
    assert not _is_app_excluded("", excluded), "empty exe must never match"
    assert not _is_app_excluded("leagueoflegends.exe", []), "empty list must exclude nothing"


def test_silence_cut():
    from speakr.streaming import find_silence_cut

    rng = np.random.default_rng(0)
    sr = 16000
    speech = (rng.standard_normal(int(3.5 * sr)) * 0.1).astype(np.float32)
    silence = (rng.standard_normal(int(0.7 * sr)) * 0.001).astype(np.float32)
    tail = (rng.standard_normal(int(2.0 * sr)) * 0.1).astype(np.float32)
    audio = np.concatenate([speech, silence, tail])
    cut = find_silence_cut(audio, sr)
    assert cut is not None, "no cut found"
    assert len(speech) <= cut <= len(speech) + len(silence), f"cut {cut} outside silence"
    # Continuous loud audio must NOT be cut mid-word.
    assert find_silence_cut(np.concatenate([speech, tail]), sr) is None


def test_notable_tokens():
    from speakr.learning import extract_notable_tokens

    tokens = extract_notable_tokens(
        "Re: Kubernetes rollout — ping @sarah-jones about the GraphQL schema and JIRA-4521 today"
    )
    assert "Kubernetes" in tokens and "GraphQL" in tokens and "JIRA-4521" in tokens, tokens
    assert "today" not in [t.lower() for t in tokens]
    assert "about" not in [t.lower() for t in tokens]


class _FakeRecorder:
    """Recorder stand-in that exposes a fixed clip as if it were live."""

    def __init__(self, audio, sample_rate=16000):
        self._audio = audio
        self.sample_rate = sample_rate

    def recorded_samples(self):
        return len(self._audio)

    def snapshot(self):
        return self._audio

    def stop_recording(self):
        return self._audio


def test_streaming_equivalence():
    import time

    from speakr.config import Config
    from speakr.dictionary import Dictionary
    from speakr.streaming import DictationSession
    from speakr.transcriber import Transcriber
    import speakr.config as cfg_mod

    wav_path = Path(sys.argv[1])
    with wave.open(str(wav_path), "rb") as wf:
        raw = wf.readframes(wf.getnframes())
    clip = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    gap = np.zeros(int(0.7 * 16000), dtype=np.float32)
    long_audio = np.concatenate([clip, gap, clip, gap, clip])

    config = Config()
    transcriber = Transcriber(config, Dictionary(cfg_mod.DICTIONARY_PATH))
    transcriber.load()

    reference = transcriber.transcribe(long_audio)

    session = DictationSession(transcriber, _FakeRecorder(long_audio), config)
    session.start()
    deadline = time.monotonic() + 20
    while session.committed == 0 and time.monotonic() < deadline:
        time.sleep(0.25)
    session.stop()
    t0 = time.monotonic()
    streamed = session.finalize()
    finalize_s = time.monotonic() - t0

    from difflib import SequenceMatcher
    import re as re_mod

    def words(t):
        return re_mod.findall(r"[a-z0-9']+", t.lower())

    similarity = SequenceMatcher(None, words(reference), words(streamed)).ratio()
    print(f"        chunks committed mid-speech: {len(session.chunks) - 1}, "
          f"finalize {finalize_s:.2f}s for {len(long_audio)/16000:.1f}s audio")
    print(f"        similarity to single-pass: {similarity:.3f}")
    assert session.committed > 0, "streaming never committed a chunk"
    assert similarity >= 0.9, f"streamed text diverged: {streamed!r} vs {reference!r}"


def test_transcription_e2e():
    from speakr.config import Config
    from speakr.dictionary import Dictionary
    from speakr.transcriber import Transcriber
    import speakr.config as cfg_mod

    wav_path = Path(sys.argv[1])
    with wave.open(str(wav_path), "rb") as wf:
        assert wf.getframerate() == 16000 and wf.getnchannels() == 1
        raw = wf.readframes(wf.getnframes())
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

    t = Transcriber(Config(), Dictionary(cfg_mod.DICTIONARY_PATH))
    t.load()
    print(f"        model device: {t.device_in_use}")
    import time

    start = time.monotonic()
    text = t.transcribe(audio)
    elapsed = time.monotonic() - start
    print(f"        transcript ({elapsed:.2f}s for {len(audio)/16000:.1f}s audio): {text!r}")
    lowered = text.lower()
    for word in ("quick", "brown", "fox"):
        assert word in lowered, f"expected {word!r} in transcript"
    assert elapsed < 10, "transcription too slow"


print("Speakr smoke test")
check("imports", test_imports)
check("formatter rules", test_formatter_rules)
check("voice commands", test_voice_commands)
check("silence-cut detection", test_silence_cut)
check("notable-token extraction", test_notable_tokens)
check("vocabulary learning", test_vocab_learning)
check("ollama formatting", test_ollama_formatting)
check("personal dictionary", test_dictionary)
check("active-app detection", test_active_app)
check("clipboard roundtrip", test_clipboard_roundtrip)
check("config defaults", test_config_defaults)
check("hotkey exclusion logic", test_hotkey_exclusion)
if len(sys.argv) > 1:
    check("transcription end-to-end", test_transcription_e2e)
    check("streaming equivalence", test_streaming_equivalence)
else:
    print("  SKIP  transcription end-to-end (no wav path given)")
    print("  SKIP  streaming equivalence (no wav path given)")

print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
