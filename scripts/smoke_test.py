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
check("vocabulary learning", test_vocab_learning)
check("ollama formatting", test_ollama_formatting)
check("personal dictionary", test_dictionary)
check("active-app detection", test_active_app)
check("clipboard roundtrip", test_clipboard_roundtrip)
check("config defaults", test_config_defaults)
if len(sys.argv) > 1:
    check("transcription end-to-end", test_transcription_e2e)
else:
    print("  SKIP  transcription end-to-end (no wav path given)")

print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
