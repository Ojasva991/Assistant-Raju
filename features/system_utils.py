"""
features/system_utils.py
Small local system utilities: battery/RAM/CPU stats, screenshots, clipboard read.

Install: pip install psutil pyautogui pyperclip

pyautogui and pyperclip are imported only when used. Why: pyautogui needs
a real desktop, so a top-level import would crash the whole assistant
(and the tests) on a machine without one.
"""

import datetime
import logging
import os

import psutil

import config

log = logging.getLogger(__name__)


class SystemUtilsFeature:
    def __init__(self, voice):
        self.voice = voice

    def report_stats(self):
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory().percent
        battery = psutil.sensors_battery()

        msg = f"CPU usage is {cpu} percent. RAM usage is {ram} percent."
        if battery:
            msg += f" Battery is at {battery.percent} percent"
            msg += ", and charging." if battery.power_plugged else "."
        self.voice.speak(msg)

    def take_screenshot(self):
        try:
            import pyautogui
        except Exception as e:  # ImportError, or no display
            log.error("pyautogui not usable: %s", e)
            self.voice.speak("I can't take screenshots. The pyautogui package is missing "
                             "or there is no screen. Install it with pip install pyautogui.")
            return
        filename = f"screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = os.path.join(config.SCREENSHOT_DIR, filename)
        img = pyautogui.screenshot()
        img.save(filepath)
        self.voice.speak(f"Screenshot saved as {filename}")

    def read_clipboard(self):
        try:
            import pyperclip
        except ImportError:
            self.voice.speak("I can't read the clipboard. Install it with pip install pyperclip.")
            return
        text = pyperclip.paste()
        if text:
            self.voice.speak(f"Your clipboard contains: {text[:200]}")
        else:
            self.voice.speak("Your clipboard is empty.")
