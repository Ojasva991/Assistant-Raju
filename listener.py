"""
listener.py
Speech-to-text via the microphone (spec section F).

  - Calibrates for background noise ONCE (at the first listen), not on every
    call. That saved about half a second per command.
  - With allow_text_fallback=False (GUI mode) it NEVER calls input(): on a
    microphone problem it calls on_error(message) and returns "".
    With allow_text_fallback=True (console) it falls back to typing.
  - The recognizer is chosen by config.STT_ENGINE (only "google" for now,
    which needs internet).

Heard text is NOT written to the log here, because it may be a spoken PIN.
(The assistant logs each command itself, after it is understood.)

Install: pip install SpeechRecognition pyaudio
"""

import logging
import time
from typing import Callable, List, Optional, Tuple

import speech_recognition as sr

import config

log = logging.getLogger(__name__)


def list_input_devices() -> List[Tuple[int, str]]:
    """(index, name) of every audio INPUT device, for the Settings page.
    Returns [] when PyAudio is missing or fails (the page then says so).
    Output-only devices are skipped, because Windows lists those too."""
    try:
        pa_module = sr.Microphone.get_pyaudio()
        audio = pa_module.PyAudio()
    except Exception:
        log.exception("Could not list microphones")
        return []
    devices = []
    try:
        for index in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(index)
            if info.get("maxInputChannels", 0) > 0:
                devices.append((index, str(info.get("name", f"Device {index}"))))
    except Exception:
        log.exception("Could not read microphone details")
    finally:
        audio.terminate()
    return devices


def why_nothing_heard(listener) -> str:
    """A short spoken reason for an empty answer, from listener.last_status."""
    status = getattr(listener, "last_status", "")
    if status == "timeout":
        return "I didn't hear anything."
    if status == "unclear":
        return "I heard you, but I couldn't make out the words."
    return "I didn't catch that."


def hear_answer(listener, secret: bool = False) -> str:
    """Listens for the answer to a question. Uses listen_answer() when the
    listener has it (the real one); simple fake listeners in tests only have listen()."""
    method = getattr(listener, "listen_answer", None)
    if method is None:
        return listener.listen()
    return method(secret=True) if secret else method()


class Listener:
    def __init__(self, use_microphone: bool = True, allow_text_fallback: bool = True,
                 on_error: Optional[Callable[[str], None]] = None,
                 recognizer=None, microphone_factory: Optional[Callable[[], object]] = None,
                 error_backoff: float = 1.0,
                 on_heard: Optional[Callable[[str], None]] = None):
        self.recognizer = recognizer or sr.Recognizer()
        self.use_microphone = use_microphone
        self.allow_text_fallback = allow_text_fallback
        self.on_error = on_error
        self.on_heard = on_heard   # optional callback(text); the UI can show what was heard
        self.device_index = config.MIC_DEVICE_INDEX   # the UI settings page can change it
        self.before_listen: Optional[Callable[[], object]] = None  # e.g. voice.wait_until_idle
        self._microphone_factory = microphone_factory or self._open_microphone
        self._error_backoff = error_backoff   # pause after an error so a broken mic cannot spin the CPU
        self._calibrated = False
        self._last_error = ""
        # Why the last listen() gave nothing: "ok", "timeout" (no speech started),
        # "unclear" (sound heard, no words recognised) or "error". Lets Raju say what went wrong.
        self.last_status = "ok"

    # ---------------- public API ----------------
    def recalibrate(self) -> None:
        """Call after the microphone device changes; the next listen calibrates again."""
        self._calibrated = False

    def listen(self, timeout: Optional[float] = None, secret: bool = False,
               report_empty: bool = False) -> str:
        """Returns what was heard, lowercase, or "" (nothing heard or an error).
        timeout = seconds to wait for speech to start (default config.LISTEN_TIMEOUT).
        secret = the text is a PIN, so it is shown as hidden.
        report_empty = also show a line when nothing was understood."""
        if not self.use_microphone:
            if self.allow_text_fallback:
                return input("You (typed): ").strip().lower()
            self._fail("The microphone is turned off. Type your command instead.", fallback=False)
            return ""

        if self.before_listen:
            try:
                self.before_listen()   # wait until Raju has finished talking
            except Exception:
                log.exception("before_listen failed")

        try:
            with self._microphone_factory() as source:
                if not self._calibrated:
                    self.recognizer.adjust_for_ambient_noise(source, duration=config.AMBIENT_SECONDS)
                    self._calibrated = True
                audio = self.recognizer.listen(source, timeout=timeout or config.LISTEN_TIMEOUT,
                                               phrase_time_limit=config.PHRASE_TIME_LIMIT)
        except sr.WaitTimeoutError:
            self.last_status = "timeout"
            log.info("listen: no speech started within the time limit")
            if report_empty:
                self._show_heard("(nothing heard: speech did not start in time)")
            return ""  # nobody spoke: not an error
        except Exception as e:  # no device, PyAudio missing, permission denied ...
            return self._mic_failed(e)

        try:
            text = self._recognize(audio)
        except sr.UnknownValueError:
            self.last_status = "unclear"
            log.info("listen: sound heard but no words recognised")
            if report_empty:
                self._show_heard("(sound heard, but the words were not understood)")
            return ""  # heard sound but no words: not an error
        except sr.RequestError as e:
            log.warning("Speech service error: %s", e)
            return self._fail("The speech service is not reachable. Check your internet "
                              "connection, or type your command.")
        except ValueError as e:  # unknown STT_ENGINE
            return self._fail(str(e), fallback=False)

        self._last_error = ""  # working again: the next error may be reported again
        self.last_status = "ok"
        if secret and not config.SHOW_SPOKEN_PIN:
            self._show_heard("(hidden, because it is a PIN)")
        else:
            self._show_heard(text.lower())
        return text.lower()

    def listen_answer(self, secret: bool = False) -> str:
        """For the ANSWER to a question Raju just asked (name, PIN, task ...):
        waits longer for you to start, and drops a leading "raju" because people
        say the wake word out of habit ("raju 7286" -> "7286")."""
        words = self.listen(timeout=config.ANSWER_TIMEOUT, secret=secret, report_empty=True).split()
        if words and words[0].strip(",.!?") == config.WAKE_WORD:
            words = words[1:]
        return " ".join(words)

    # ---------------- internals ----------------
    def _show_heard(self, text: str) -> None:
        """Shows what the microphone understood. The text is NOT written to the log
        (it could be a PIN)."""
        if self.on_heard:
            try:
                self.on_heard(text)
            except Exception:
                log.exception("on_heard callback failed")
        elif config.SHOW_HEARD and self.allow_text_fallback:   # console mode only
            try:
                print(f"Heard: {text}")
            except UnicodeEncodeError:
                print(f"Heard: {text}".encode("ascii", "replace").decode("ascii"))

    def _open_microphone(self):
        return sr.Microphone(device_index=self.device_index)

    def _recognize(self, audio) -> str:
        if config.STT_ENGINE == "google":
            return self.recognizer.recognize_google(audio, language=config.STT_LANGUAGE)
        raise ValueError(f"Unknown speech engine '{config.STT_ENGINE}' in config.STT_ENGINE.")

    def _mic_failed(self, error: Exception) -> str:
        log.warning("Microphone error: %s", error)
        return self._fail("Microphone not found or blocked. Open Settings and choose another "
                          "device, or check the Windows microphone privacy settings.")

    def _fail(self, message: str, fallback: bool = True) -> str:
        """Reports an error once (not on every retry). In console mode it can
        fall back to typing; in GUI mode it returns "" and the UI shows the message."""
        self.last_status = "error"
        if message != self._last_error:
            self._last_error = message
            if self.on_error:
                try:
                    self.on_error(message)
                except Exception:
                    log.exception("on_error callback failed")
        if fallback and self.allow_text_fallback:
            print(f"[Listener] {message}")
            return input("You (typed): ").strip().lower()
        if self._error_backoff:
            time.sleep(self._error_backoff)
        return ""
