"""Runs tools/smoke_test.py (safe mode) inside pytest, so one command checks everything."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import smoke_test  # noqa: E402


def test_smoke_test_has_no_failures():
    report = smoke_test.run_smoke()
    failed = [(name, detail) for name, status, detail in report.rows if status == smoke_test.FAIL]
    assert not failed, failed
    assert report.count(smoke_test.PASS) >= 15


def test_smoke_test_reports_a_failure(monkeypatch):
    # A broken check must show up as FAIL and give exit code 1, never be hidden.
    def broken():
        raise RuntimeError("boom")
    monkeypatch.setattr(smoke_test, "check_config", broken)
    report = smoke_test.run_smoke()
    assert report.count(smoke_test.FAIL) == 1
    assert smoke_test.main([]) == 1


def test_online_check_treats_http_error_as_reachable(monkeypatch):
    # Wikipedia answering "403" still proves the internet works.
    import urllib.error
    import urllib.request

    def refuse(*args, **kwargs):
        raise urllib.error.HTTPError("https://x", 403, "Forbidden", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    assert isinstance(smoke_test.check_online(), str)  # a plain string means PASS


def test_online_check_warns_when_really_offline(monkeypatch):
    import urllib.error
    import urllib.request

    def offline(*args, **kwargs):
        raise urllib.error.URLError("no network")
    monkeypatch.setattr(urllib.request, "urlopen", offline)
    status, _ = smoke_test.check_online()
    assert status == smoke_test.WARN


def test_audio_level_tells_silence_from_sound():
    import math
    import struct
    import speech_recognition as sr
    rate = 16000
    silent = sr.AudioData(b"\x00\x00" * rate, rate, 2)
    tone = sr.AudioData(b"".join(struct.pack("<h", int(8000 * math.sin(i / 10))) for i in range(rate)), rate, 2)
    seconds, level_silent = smoke_test.audio_level(silent)
    _, level_tone = smoke_test.audio_level(tone)
    assert abs(seconds - 1.0) < 0.01
    assert level_silent < smoke_test.QUIET_LEVEL < level_tone
