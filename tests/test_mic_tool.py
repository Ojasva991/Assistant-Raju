"""tools/mic_test.py: device choice, result codes and exit codes.
No real microphone: speech_recognition is replaced by small fakes."""
import argparse
import os
import sys

import pytest
import speech_recognition as sr

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import config  # noqa: E402
import mic_test  # noqa: E402

INPUTS = [(1, "Mic A"), (5, "Mic B"), (9, "Mic C")]


def args(**kw):
    base = dict(list=False, device=None, all=False)
    base.update(kw)
    return argparse.Namespace(**base)


# ---------------- which devices are tested ----------------
def test_all_tests_every_input_device():
    assert mic_test.pick_devices(args(all=True), INPUTS) == [1, 5, 9]


def test_device_option_tests_only_that_index():
    assert mic_test.pick_devices(args(device=5), INPUTS) == [5]


def test_default_is_the_index_from_config(monkeypatch):
    monkeypatch.setattr(config, "MIC_DEVICE_INDEX", 9)
    assert mic_test.pick_devices(args(), INPUTS) == [9]


def test_none_in_config_means_system_default(monkeypatch):
    monkeypatch.setattr(config, "MIC_DEVICE_INDEX", None)
    assert mic_test.pick_devices(args(), INPUTS) == []


# ---------------- one device test ----------------
class FakeAudio:
    frame_data = b"\x00\x00" * 100
    sample_width = 2


class FakeMic:
    def __init__(self, device_index=None):
        self.device_index = device_index
        if FakeMic.open_error:
            raise FakeMic.open_error

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeRecognizer:
    energy_threshold = 300

    def adjust_for_ambient_noise(self, source, duration=1):
        pass

    def listen(self, source, timeout=None, phrase_time_limit=None):
        if FakeRecognizer.listen_error:
            raise FakeRecognizer.listen_error
        return FakeAudio()

    def recognize_google(self, audio, language=None):
        if FakeRecognizer.google_error:
            raise FakeRecognizer.google_error
        return "hello raju"


@pytest.fixture
def fake_sr(monkeypatch):
    FakeMic.open_error = None
    FakeRecognizer.listen_error = None
    FakeRecognizer.google_error = None
    monkeypatch.setattr(sr, "Microphone", FakeMic)
    monkeypatch.setattr(sr, "Recognizer", FakeRecognizer)
    monkeypatch.setattr(mic_test, "audio_level", lambda audio: 1000)
    return None


def test_good_device_is_ok(fake_sr, capsys):
    assert mic_test.test_device(1) == "ok"
    assert "hello raju" in capsys.readouterr().out


def test_no_speech_is_silent(fake_sr):
    FakeRecognizer.listen_error = sr.WaitTimeoutError()
    assert mic_test.test_device(1) == "silent"


def test_unreadable_loud_audio_is_unclear(fake_sr):
    FakeRecognizer.google_error = sr.UnknownValueError()
    assert mic_test.test_device(1) == "unclear"


def test_unreadable_quiet_audio_is_quiet(fake_sr, monkeypatch):
    FakeRecognizer.google_error = sr.UnknownValueError()
    monkeypatch.setattr(mic_test, "audio_level", lambda audio: 10)
    assert mic_test.test_device(1) == "quiet"


def test_google_down_is_offline_not_a_mic_fault(fake_sr):
    FakeRecognizer.google_error = sr.RequestError("no internet")
    assert mic_test.test_device(1) == "offline"


def test_device_that_cannot_open_is_error(fake_sr):
    FakeMic.open_error = OSError("busy")
    assert mic_test.test_device(1) == "error"


# ---------------- whole tool ----------------
def test_list_returns_1_when_no_device(monkeypatch):
    import listener
    monkeypatch.setattr(listener, "list_input_devices", lambda: [])
    assert mic_test.main(["--list"]) == 1


def test_list_returns_0_with_devices(monkeypatch, capsys):
    import listener
    monkeypatch.setattr(listener, "list_input_devices", lambda: INPUTS)
    assert mic_test.main(["--list"]) == 0
    assert "Mic B" in capsys.readouterr().out


def test_all_goes_on_after_a_bad_device_and_names_the_good_one(monkeypatch, capsys):
    import listener
    monkeypatch.setattr(listener, "list_input_devices", lambda: INPUTS)
    outcome = {1: "error", 5: "ok", 9: "silent"}
    tested = []

    def fake_test(index, seconds=5):
        tested.append(index)
        return outcome[index]
    monkeypatch.setattr(mic_test, "test_device", fake_test)
    assert mic_test.main(["--all"]) == 0
    assert tested == [1, 5, 9]                      # every device was tried
    assert "MIC_DEVICE_INDEX = 5" in capsys.readouterr().out


def test_exit_code_is_1_when_no_device_understood(monkeypatch):
    import listener
    monkeypatch.setattr(listener, "list_input_devices", lambda: INPUTS)
    monkeypatch.setattr(mic_test, "test_device", lambda index, seconds=5: "unclear")
    assert mic_test.main(["--all"]) == 1


def test_all_with_no_devices_does_not_crash(monkeypatch):
    import listener
    monkeypatch.setattr(listener, "list_input_devices", lambda: [])
    assert mic_test.main(["--all"]) == 1
