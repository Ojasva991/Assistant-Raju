"""
gui.py
A simple Tkinter front-end for Raju, so you're not stuck staring at a
black terminal window during demos.

Run:
    python gui.py

Features:
    - Mic button: listens once, executes the command
    - Text box: type a command instead of speaking (works even with
      no mic at all)
    - Continuous mode checkbox: keeps listening automatically after
      each command
    - Scrolling transcript log of the whole conversation
    - Status line: Idle / Listening / Thinking / Speaking
    - System tray icon: closing the window minimizes to the tray
      instead of quitting, so Raju keeps running (and keeps listening,
      if continuous mode is on) in the background. Right-click the
      tray icon for Show / Quit.

Threading note: speech recognition and TTS both block, so every
listen/execute cycle runs in a background thread. The background
thread never touches Tkinter widgets directly — it only pushes
messages onto a queue, and the GUI polls that queue on the main
thread. This is the standard safe pattern for Tkinter + threads.
The tray icon's own event loop is ALSO a separate thread (pystray
requirement), so its menu callbacks use root.after(0, ...) to safely
hand control back to the main thread too — same pattern, same reason.
"""

import queue
import threading
import tkinter as tk
from tkinter import scrolledtext, ttk

import pystray
from PIL import Image, ImageDraw

from assistant import J
import config


class JGui:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{config.ASSISTANT_NAME} — Voice Assistant")
        self.root.geometry("560x520")
        self.root.minsize(480, 420)

        self.msg_queue = queue.Queue()
        self.continuous_mode = tk.BooleanVar(value=False)
        self._busy = False  # true while a listen/execute cycle is running

        self._build_widgets()

        # J's speak() calls will push text into the queue via this callback,
        # instead of (or as well as) printing to console.
        self.assistant = J(use_microphone=True, on_speak=self._on_speak)

        self._log(config.ASSISTANT_NAME, f'Hello, I am {config.ASSISTANT_NAME}. Click the mic and say '
                   f'"{config.WAKE_WORD}" before your command, or type below.')

        self.tray_icon = None
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)
        self._start_tray_icon()

        self._poll_queue()

    # ---------------- SYSTEM TRAY ----------------
    def _build_tray_image(self):
        """Draws a simple round icon with the assistant's initial —
        no image file needed, generated entirely in code."""
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((2, 2, size - 2, size - 2), fill=(38, 162, 105, 255))
        initial = config.ASSISTANT_NAME[0].upper()
        # Rough centering for a single character without needing a
        # specific font file (uses Pillow's built-in default font).
        draw.text((size / 2 - 6, size / 2 - 10), initial, fill=(255, 255, 255, 255))
        return img

    def _start_tray_icon(self):
        image = self._build_tray_image()
        menu = pystray.Menu(
            pystray.MenuItem(f"Show {config.ASSISTANT_NAME}", self._tray_show, default=True),
            pystray.MenuItem("Quit", self._tray_quit),
        )
        self.tray_icon = pystray.Icon(config.ASSISTANT_NAME.lower(), image,
                                       f"{config.ASSISTANT_NAME} Assistant", menu)
        # pystray's .run() blocks and needs its own thread; the window
        # manager / tray on some platforms also requires it NOT be the
        # main thread when Tkinter also has a mainloop running.
        thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        thread.start()

    def _on_window_close(self):
        """Closing the window (the X button) minimizes to tray instead
        of quitting, so Raju keeps running -- and keeps listening, if
        continuous mode is on -- in the background."""
        self._log("System", "Minimized to tray. Right-click the tray icon to reopen or quit.")
        self.root.withdraw()

    def _tray_show(self, icon=None, item=None):
        # Called from pystray's own thread -- must hand off to the
        # Tkinter main thread via root.after(), same rule as the
        # speech/listen background threads use.
        self.root.after(0, self.root.deiconify)

    def _tray_quit(self, icon=None, item=None):
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.after(0, self.root.destroy)

    # ---------------- UI LAYOUT ----------------
    def _build_widgets(self):
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(fill="x")

        self.status_label = ttk.Label(
            top_frame, text="Status: Idle", font=("Segoe UI", 11, "bold")
        )
        self.status_label.pack(side="left")

        self.continuous_check = ttk.Checkbutton(
            top_frame, text="Continuous listening", variable=self.continuous_mode
        )
        self.continuous_check.pack(side="right")

        self.log_box = scrolledtext.ScrolledText(
            self.root, wrap="word", state="disabled", font=("Segoe UI", 10)
        )
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log_box.tag_config("user", foreground="#1a5fb4")
        self.log_box.tag_config("j", foreground="#26a269")
        self.log_box.tag_config("system", foreground="#888888")

        bottom_frame = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        bottom_frame.pack(fill="x")

        self.entry = ttk.Entry(bottom_frame)
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry.bind("<Return>", lambda event: self._on_send_text())

        self.send_button = ttk.Button(bottom_frame, text="Send", command=self._on_send_text)
        self.send_button.pack(side="left", padx=(0, 8))

        self.mic_button = ttk.Button(bottom_frame, text="🎤 Listen", command=self._on_mic_click)
        self.mic_button.pack(side="left")

    # ---------------- LOGGING ----------------
    def _log(self, speaker, text):
        self.log_box.configure(state="normal")
        tag = "user" if speaker == "You" else ("j" if speaker == config.ASSISTANT_NAME else "system")
        self.log_box.insert("end", f"{speaker}: {text}\n", tag)
        self.log_box.configure(state="disabled")
        self.log_box.see("end")

    def _set_status(self, text):
        self.status_label.config(text=f"Status: {text}")

    # ---------------- CALLBACK FROM BACKGROUND THREAD ----------------
    def _on_speak(self, text):
        """Called by SpeechEngine.speak() — may run on a background thread,
        so just queue it; never touch widgets here directly."""
        self.msg_queue.put(("speak", text))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "speak":
                    self._log(config.ASSISTANT_NAME, payload)
                elif kind == "status":
                    self._set_status(payload)
                elif kind == "user_said":
                    self._log("You", payload)
                elif kind == "cycle_done":
                    self._busy = False
                    self._set_status("Idle")
                    if self.continuous_mode.get():
                        self._start_listen_thread()
                elif kind == "exit":
                    self._log("System", "Session ended.")
                    self.mic_button.config(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    # ---------------- BUTTON HANDLERS ----------------
    def _on_mic_click(self):
        if self._busy:
            return
        self._start_listen_thread()

    def _start_listen_thread(self):
        self._busy = True
        thread = threading.Thread(target=self._listen_and_execute, daemon=True)
        thread.start()

    def _listen_and_execute(self):
        self.msg_queue.put(("status", f'Listening for "{config.WAKE_WORD}"...'))
        query = self.assistant.listen_for_command()
        if query:
            self.msg_queue.put(("user_said", query))
            self.msg_queue.put(("status", "Thinking..."))
            self._run_execute(query)
        self.msg_queue.put(("cycle_done", None))

    def _on_send_text(self):
        text = self.entry.get().strip()
        if not text or self._busy:
            return
        self.entry.delete(0, "end")
        self.msg_queue.put(("user_said", text))
        self._busy = True
        thread = threading.Thread(target=self._execute_typed, args=(text,), daemon=True)
        thread.start()

    def _execute_typed(self, text):
        self.msg_queue.put(("status", "Thinking..."))
        self._run_execute(text)
        self.msg_queue.put(("cycle_done", None))

    def _run_execute(self, query):
        try:
            self.assistant.execute(query)
        except SystemExit:
            self.msg_queue.put(("exit", None))
        except Exception as e:
            self.msg_queue.put(("speak", f"Something went wrong: {e}"))


def main():
    root = tk.Tk()
    JGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
