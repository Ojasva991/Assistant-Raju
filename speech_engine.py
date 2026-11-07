"""
speech_engine.py
Text-to-speech with ONE worker thread and a queue (spec section F).

Why: Raju can speak from several threads (the main command loop, the
reminder thread, later the UI). Before, two of them could talk at the
same time. Now every sentence goes into a queue and one worker thread
speaks them one by one. speak() still BLOCKS until its own sentence is
finished, so replies never overlap and the mic is not open while Raju talks.

Note: pyttsx3's SAPI5 driver on Windows has a known bug where reusing one
engine across several speak() calls makes it go silent after the first
sentence. The fix is to create a fresh engine for each sentence, which the
worker does.

Install: pip install pyttsx3
"""

import logging
import queue
import sys
import threading
from typing import Callable, Optional, Tuple

import config

log = logging.getLogger(__name__)


def _default_engine_factory():
    import pyttsx3  # imported late: a missing package must not stop Raju starting
    return pyttsx3.init()


class SpeechEngine:
    def __init__(self, rate=175, volume=1.0, on_speak: Optional[Callable[[str], None]] = None,
                 engine_factory: Optional[Callable[[], object]] = None, muted: bool = False):
        self.rate = rate
        self.volume = volume
        self.on_speak = on_speak    # optional callback(text) -- used by the UI
        self.muted = muted          # the UI setting "speak replies": text still shows, no sound
        self._engine_factory = engine_factory or _default_engine_factory
        self._queue: "queue.Queue[Optional[Tuple[str, threading.Event]]]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._thread_lock = threading.Lock()
        self._pending = 0                      # sentences waiting or being spoken
        self._pending_lock = threading.Lock()
        self._idle = threading.Event()         # set while nothing is being spoken
        self._idle.set()
        self._broken = False                   # True if pyttsx3 cannot be imported

    # ---------------- public API ----------------
    def speak(self, text: str) -> None:
        """Shows the sentence, then speaks it. Returns when it has been spoken
        (or at once when muted)."""
        text = (text or "").strip()
        if not text:
            return
        self._show(text)
        if self.muted or self._broken:
            return

        done = threading.Event()
        self._start_worker()
        with self._pending_lock:
            self._pending += 1
            self._idle.clear()
        self._queue.put((text, done))
        if not done.wait(timeout=config.TTS_TIMEOUT):
            log.warning("Speaking took longer than %s s; continuing without waiting",
                        config.TTS_TIMEOUT)

    def wait_until_idle(self, timeout: Optional[float] = None) -> bool:
        """Blocks until Raju has stopped talking. The listener calls this
        before opening the mic, so a reminder spoken in the background is
        not heard as a command."""
        return self._idle.wait(timeout)

    def close(self) -> None:
        """Stops the worker thread (optional; it is a daemon thread anyway)."""
        with self._thread_lock:
            thread, self._thread = self._thread, None
        if thread and thread.is_alive():
            self._queue.put(None)
            thread.join(timeout=2)

    # ---------------- internals ----------------
    def _show(self, text: str) -> None:
        # Console mode has no window, so the reply is also printed. A Windows
        # console can fail on unusual letters, so fall back to '?' for them.
        line = f"{config.ASSISTANT_NAME}: {text}"
        try:
            print(line)
        except UnicodeEncodeError:
            print(line.encode("ascii", "replace").decode("ascii"))
        log.info("spoke: %s", text)
        if self.on_speak:
            try:
                self.on_speak(text)
            except Exception:
                log.exception("on_speak callback failed")

    def _start_worker(self) -> None:
        with self._thread_lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._worker, name="speech-worker",
                                                daemon=True)
                self._thread.start()

    def _worker(self) -> None:
        com_started = self._com_start()
        try:
            while True:
                item = self._queue.get()
                if item is None:           # sentinel from close()
                    break
                text, done = item
                try:
                    self._say(text)
                except Exception:
                    log.exception("Text to speech failed")
                finally:
                    done.set()
                    self._finished_one()
        finally:
            # Free anyone still waiting if the worker ends early.
            while True:
                try:
                    item = self._queue.get_nowait()
                except queue.Empty:
                    break
                if item is not None:
                    item[1].set()
                    self._finished_one()
            if com_started:
                self._com_stop()

    def _finished_one(self) -> None:
        with self._pending_lock:
            self._pending -= 1
            if self._pending <= 0:
                self._pending = 0
                self._idle.set()

    def _say(self, text: str) -> None:
        try:
            engine = self._engine_factory()   # a fresh engine for every sentence
        except ImportError:
            self._broken = True
            log.error("pyttsx3 is not installed (pip install pyttsx3); Raju will only show text")
            return
        try:
            engine.setProperty("rate", self.rate)
            engine.setProperty("volume", self.volume)
            engine.say(text)
            engine.runAndWait()
        finally:
            try:
                engine.stop()
            except Exception:
                pass

    @staticmethod
    def _com_start() -> bool:
        """On Windows, a thread that uses SAPI (COM) should initialise COM
        first. pywin32 comes with pyttsx3 on Windows; if it is missing we skip."""
        if not sys.platform.startswith("win"):
            return False
        try:
            import pythoncom
            pythoncom.CoInitialize()
            return True
        except Exception:
            return False

    @staticmethod
    def _com_stop() -> None:
        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except Exception:
            pass
