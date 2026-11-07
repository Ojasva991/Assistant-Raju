"""Tests for section F: the speech queue and the listener.
No speakers and no microphone: a fake pyttsx3 engine, a fake recognizer and mic."""

import builtins
import logging
import threading
import time

import pytest
import speech_recognition as sr

import config
from listener import Listener
from speech_engine import SpeechEngine


# ---------------- fake text-to-speech engine ----------------
class Tracker:
    """Records what the fake engines spoke and whether two spoke at once."""

    def __init__(self, delay=0.03):
        self.delay = delay
        self.spoken = []
        self.created = 0
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()
        self.fail_on = set()
        self.threads = set()

    def factory(self):
        self.created += 1
        return FakeEngine(self)


class FakeEngine:
    def __init__(self, tracker):
        self.t = tracker
        self.text = ""

    def setProperty(self, name, value):
        pass

    def say(self, text):
        self.text = text

    def runAndWait(self):
        t = self.t
        with t.lock:
            t.active += 1
            t.max_active = max(t.max_active, t.active)
            t.threads.add(threading.current_thread().name)
        try:
            if self.text in t.fail_on:
                raise RuntimeError("driver crashed")
            time.sleep(t.delay)
            t.spoken.append(self.text)
        finally:
            with t.lock:
                t.active -= 1

    def stop(self):
        pass


@pytest.fixture
def engine():
    tracker = Tracker()
    voice = SpeechEngine(engine_factory=tracker.factory)
    yield voice, tracker
    voice.close()


def test_speak_blocks_until_the_sentence_is_finished(engine):
    voice, tracker = engine
    voice.speak("hello")
    assert tracker.spoken == ["hello"]       # already spoken when speak() returned


def test_sentences_from_many_threads_never_overlap(engine):
    voice, tracker = engine
    threads = [threading.Thread(target=voice.speak, args=(f"sentence {i}",)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert sorted(tracker.spoken) == sorted(f"sentence {i}" for i in range(6))
    assert tracker.max_active == 1           # never two voices at the same time


def test_one_worker_thread_does_all_the_speaking(engine):
    voice, tracker = engine
    for i in range(3):
        voice.speak(f"s{i}")
    assert tracker.threads == {"speech-worker"}


def test_fresh_engine_for_every_sentence(engine):
    voice, tracker = engine
    voice.speak("one")
    voice.speak("two")
    assert tracker.created == 2              # the Windows "goes silent" workaround


def test_order_is_kept_for_one_caller(engine):
    voice, tracker = engine
    for word in ("a", "b", "c"):
        voice.speak(word)
    assert tracker.spoken == ["a", "b", "c"]


def test_muted_shows_text_but_makes_no_sound():
    tracker = Tracker()
    shown = []
    voice = SpeechEngine(on_speak=shown.append, engine_factory=tracker.factory, muted=True)
    voice.speak("silent reply")
    assert shown == ["silent reply"]
    assert tracker.created == 0
    voice.muted = False                       # the UI can switch it back on
    voice.speak("loud reply")
    assert tracker.spoken == ["loud reply"]
    voice.close()


def test_on_speak_gets_the_text_before_speaking(engine):
    voice, tracker = engine
    seen = []
    voice.on_speak = lambda text: seen.append((text, list(tracker.spoken)))
    voice.speak("hi")
    assert seen == [("hi", [])]


def test_failing_callback_or_engine_does_not_break_speaking(engine):
    voice, tracker = engine
    voice.on_speak = lambda text: 1 / 0
    tracker.fail_on = {"bad"}
    voice.speak("bad")                        # the engine raises: speak() still returns
    voice.speak("good")                       # and the worker is still alive
    assert tracker.spoken == ["good"]


def test_empty_text_is_ignored(engine):
    voice, tracker = engine
    voice.speak("")
    voice.speak("   ")
    voice.speak(None)
    assert tracker.created == 0


def test_wait_until_idle(engine):
    voice, tracker = engine
    tracker.delay = 0.2
    assert voice.wait_until_idle(0) is True   # nothing is being said
    t = threading.Thread(target=voice.speak, args=("long sentence",))
    t.start()
    time.sleep(0.05)
    assert voice.wait_until_idle(0) is False  # Raju is talking: the mic must wait
    assert voice.wait_until_idle(3) is True
    t.join()


def test_close_and_speak_again(engine):
    voice, tracker = engine
    voice.speak("one")
    voice.close()
    voice.speak("two")                        # a new worker starts by itself
    assert tracker.spoken == ["one", "two"]


def test_missing_pyttsx3_does_not_crash():
    def no_package():
        raise ImportError("No module named pyttsx3")
    shown = []
    voice = SpeechEngine(on_speak=shown.append, engine_factory=no_package)
    voice.speak("first")
    voice.speak("second")
    assert shown == ["first", "second"]       # text still reaches the screen
    voice.close()


def test_unusual_letters_do_not_crash_a_windows_console(monkeypatch):
    real_print = builtins.print

    def cp1252_console(text, *args, **kwargs):
        text.encode("ascii")                  # raises UnicodeEncodeError for non-ASCII
        real_print(text, *args, **kwargs)
    monkeypatch.setattr(builtins, "print", cp1252_console)
    voice = SpeechEngine(engine_factory=Tracker(0).factory, muted=True)
    voice.speak("Śrīnivāsa Rāmānujan was a mathematician")   # must not raise


# ---------------- listener ----------------
class FakeMic:
    def __init__(self, log, fail=None):
        self.log, self.fail = log, fail

    def __enter__(self):
        if self.fail:
            raise self.fail
        self.log.append("open")
        return self

    def __exit__(self, *args):
        return False


class FakeRecognizer:
    def __init__(self, results=("open notepad",)):
        self.results = list(results)
        self.calibrations = 0
        self.log = []

    def adjust_for_ambient_noise(self, source, duration=1):
        self.calibrations += 1

    def listen(self, source, timeout=None, phrase_time_limit=None):
        self.log.append(("listen", timeout, phrase_time_limit))
        return "audio"

    def recognize_google(self, audio, language=None):
        self.log.append(("google", language))
        result = self.results.pop(0) if self.results else "open notepad"
        if isinstance(result, Exception):
            raise result
        return result


def make_listener(results=("Open Notepad",), mic_error=None, **kwargs):
    log = []
    recognizer = FakeRecognizer(results)
    kwargs.setdefault("error_backoff", 0)
    listener = Listener(recognizer=recognizer, microphone_factory=lambda: FakeMic(log, mic_error),
                        **kwargs)
    return listener, recognizer, log


@pytest.fixture
def no_input(monkeypatch):
    def forbidden(prompt=""):
        raise AssertionError("input() must never be called in GUI mode")
    monkeypatch.setattr(builtins, "input", forbidden)


def test_returns_lowercase_text():
    listener, _, _ = make_listener(["Open NOTEPAD"])
    assert listener.listen() == "open notepad"


def test_noise_calibration_happens_once():
    listener, recognizer, _ = make_listener(["a", "b", "c"])
    for _ in range(3):
        listener.listen()
    assert recognizer.calibrations == 1
    listener.recalibrate()                    # e.g. the mic device was changed
    listener.listen()
    assert recognizer.calibrations == 2


def test_uses_the_configured_engine_settings():
    listener, recognizer, _ = make_listener()
    listener.listen()
    assert ("listen", config.LISTEN_TIMEOUT, config.PHRASE_TIME_LIMIT) in recognizer.log
    assert ("google", config.STT_LANGUAGE) in recognizer.log
    assert listener.device_index == config.MIC_DEVICE_INDEX


def test_unknown_engine_name_is_reported(monkeypatch, no_input):
    monkeypatch.setattr(config, "STT_ENGINE", "vosk")
    errors = []
    listener, _, _ = make_listener(allow_text_fallback=False, on_error=errors.append)
    assert listener.listen() == ""
    assert "vosk" in errors[0]


@pytest.mark.parametrize("problem", [sr.WaitTimeoutError(), sr.UnknownValueError()])
def test_silence_and_unclear_speech_are_not_errors(problem, no_input):
    errors = []
    if isinstance(problem, sr.WaitTimeoutError):
        listener, _, _ = make_listener(mic_error=problem, allow_text_fallback=False,
                                       on_error=errors.append)
    else:
        listener, _, _ = make_listener([problem], allow_text_fallback=False, on_error=errors.append)
    assert listener.listen() == ""
    assert errors == []


def test_mic_failure_in_gui_mode_calls_on_error_and_never_input(no_input):
    errors = []
    listener, _, _ = make_listener(mic_error=OSError("no device"), allow_text_fallback=False,
                                   on_error=errors.append)
    assert listener.listen() == ""
    assert len(errors) == 1 and "Microphone" in errors[0]


def test_same_error_is_reported_once_until_the_mic_works_again(no_input):
    errors = []
    listener, _, log = make_listener(mic_error=OSError("no device"), allow_text_fallback=False,
                                     on_error=errors.append)
    for _ in range(4):
        listener.listen()
    assert len(errors) == 1                   # no spam in the chat window
    listener._microphone_factory = lambda: FakeMic(log)   # the mic comes back
    assert listener.listen() == "open notepad"
    listener._microphone_factory = lambda: FakeMic(log, OSError("gone again"))
    listener.listen()
    assert len(errors) == 2


def test_no_internet_message(no_input):
    errors = []
    listener, _, _ = make_listener([sr.RequestError("offline")], allow_text_fallback=False,
                                   on_error=errors.append)
    assert listener.listen() == ""
    assert "internet" in errors[0]


def test_console_mode_falls_back_to_typing(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda prompt="": "  Open Notepad ")
    listener, _, _ = make_listener(mic_error=OSError("no device"), allow_text_fallback=True)
    assert listener.listen() == "open notepad"


def test_text_mode_types_when_the_mic_is_off(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda prompt="": "What Time")
    listener, _, _ = make_listener(use_microphone=False)
    assert listener.listen() == "what time"


def test_mic_off_in_gui_mode_does_not_block(no_input):
    errors = []
    listener, _, _ = make_listener(use_microphone=False, allow_text_fallback=False,
                                   on_error=errors.append)
    assert listener.listen() == ""
    assert "turned off" in errors[0]


def test_waits_for_raju_to_stop_talking_before_opening_the_mic():
    order = []
    listener, _, log = make_listener()
    listener.before_listen = lambda: order.append("waited")
    real_factory = listener._microphone_factory
    listener._microphone_factory = lambda: (order.append("mic opened"), real_factory())[1]
    listener.listen()
    assert order == ["waited", "mic opened"]


def test_heard_text_is_never_logged(caplog):
    # What was heard could be a spoken PIN.
    listener, _, _ = make_listener(["my pin is 4 7 1 1"])
    with caplog.at_level(logging.DEBUG):
        listener.listen()
    assert "4 7 1 1" not in caplog.text


# ---------------- answers to Raju's questions ----------------
def test_answers_get_more_time_than_wake_word_listening():
    listener, recognizer, _ = make_listener(["my name is ojas"])
    assert listener.listen_answer() == "my name is ojas"
    assert ("listen", config.ANSWER_TIMEOUT, config.PHRASE_TIME_LIMIT) in recognizer.log
    assert config.ANSWER_TIMEOUT > config.LISTEN_TIMEOUT


def test_wake_word_said_out_of_habit_is_dropped_from_an_answer():
    listener, _, _ = make_listener(["raju 7286"])
    assert listener.listen_answer() == "7286"
    listener, _, _ = make_listener(["raj kumar"])         # a name starting with raj is kept
    assert listener.listen_answer() == "raj kumar"


def test_hear_answer_works_with_simple_fake_listeners():
    from listener import hear_answer

    class OnlyListen:
        def listen(self):
            return "yes"
    assert hear_answer(OnlyListen()) == "yes"


# ---------------- why nothing was heard ----------------
def test_last_status_tells_silence_from_unclear_speech_from_errors():
    listener, _, _ = make_listener(["hello"])
    listener.listen()
    assert listener.last_status == "ok"

    listener, _, _ = make_listener(mic_error=sr.WaitTimeoutError(), allow_text_fallback=False)
    assert listener.listen() == "" and listener.last_status == "timeout"

    listener, _, _ = make_listener([sr.UnknownValueError()], allow_text_fallback=False)
    assert listener.listen() == "" and listener.last_status == "unclear"

    listener, _, _ = make_listener(mic_error=OSError("no device"), allow_text_fallback=False)
    assert listener.listen() == "" and listener.last_status == "error"


def test_spoken_reasons():
    from listener import why_nothing_heard

    class L:
        last_status = "timeout"
    assert "didn't hear" in why_nothing_heard(L())
    L.last_status = "unclear"
    assert "make out" in why_nothing_heard(L())
    assert why_nothing_heard(object()) == "I didn't catch that."   # simple fake listeners


# ---------------- showing what was heard ----------------
def test_console_prints_what_was_heard(capsys):
    listener, _, _ = make_listener(["Open Notepad"])
    listener.listen()
    assert "Heard: open notepad" in capsys.readouterr().out


def test_pin_is_hidden_unless_testing_switch_is_on(capsys, monkeypatch):
    listener, _, _ = make_listener(["1 2 3 4"])
    listener.listen_answer(secret=True)
    out = capsys.readouterr().out
    assert "1 2 3 4" not in out and "hidden" in out

    monkeypatch.setattr(config, "SHOW_SPOKEN_PIN", True)
    listener, _, _ = make_listener(["1 2 3 4"])
    listener.listen_answer(secret=True)
    assert "Heard: 1 2 3 4" in capsys.readouterr().out


def test_answers_report_why_nothing_was_understood(capsys, no_input):
    listener, _, _ = make_listener([sr.UnknownValueError()], allow_text_fallback=True)
    listener.listen_answer()
    assert "words were not understood" in capsys.readouterr().out

    listener, _, _ = make_listener(mic_error=sr.WaitTimeoutError(), allow_text_fallback=True)
    listener.listen_answer()
    assert "did not start in time" in capsys.readouterr().out


def test_wake_word_listening_stays_quiet_when_nothing_was_said(capsys):
    listener, _, _ = make_listener(mic_error=sr.WaitTimeoutError())
    listener.listen()
    assert capsys.readouterr().out == ""      # no line every 5 seconds


def test_gui_mode_does_not_print(capsys, no_input):
    listener, _, _ = make_listener(["hello"], allow_text_fallback=False)
    listener.listen()
    assert capsys.readouterr().out == ""


def test_ui_can_receive_what_was_heard(capsys):
    shown = []
    listener, _, _ = make_listener(["hello there"], on_heard=shown.append)
    listener.listen()
    assert shown == ["hello there"] and capsys.readouterr().out == ""


def test_broken_on_heard_does_not_stop_listening():
    listener, _, _ = make_listener(["hello"], on_heard=lambda text: 1 / 0)
    assert listener.listen() == "hello"


def test_heard_switch_can_be_turned_off(capsys, monkeypatch):
    monkeypatch.setattr(config, "SHOW_HEARD", False)
    listener, _, _ = make_listener(["hello"])
    listener.listen()
    assert capsys.readouterr().out == ""


def test_hear_answer_passes_secret_only_to_pin_questions():
    from listener import hear_answer

    class Recorder:
        def __init__(self):
            self.calls = []

        def listen_answer(self, secret=False):
            self.calls.append(secret)
            return "x"
    r = Recorder()
    hear_answer(r)
    hear_answer(r, secret=True)
    assert r.calls == [False, True]
