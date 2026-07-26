"""
features/system_utils.py
Small local system utilities: battery/RAM/CPU stats, screenshots, clipboard read.

Install: pip install psutil pyautogui pyperclip
"""

import datetime
import os

import psutil
import pyautogui
import pyperclip

import config


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
        filename = f"screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = os.path.join(config.SCREENSHOT_DIR, filename)
        img = pyautogui.screenshot()
        img.save(filepath)
        self.voice.speak(f"Screenshot saved as {filename}")

    def read_clipboard(self):
        text = pyperclip.paste()
        if text:
            self.voice.speak(f"Your clipboard contains: {text[:200]}")
        else:
            self.voice.speak("Your clipboard is empty.")
