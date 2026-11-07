"""
tools/mic_test.py
One tool to find the right microphone. It replaces the old mic_test.py and
mic_device_test.py. It does not start Raju, so a problem here is a problem
with Windows, the microphone or the internet, not with the assistant code.

    python tools/mic_test.py              list devices, then test config.MIC_DEVICE_INDEX
    python tools/mic_test.py --list       only list the input devices
    python tools/mic_test.py --device 5   test one device index
    python tools/mic_test.py --all        test EVERY input device, one after the other

For each device it records one phrase, prints the sound level, and asks
Google to turn the audio into text (needs internet). Exit code 1 if no
tested device understood you.
"""

import argparse
import os
import sys
from typing import List, Optional, Sequence, Tuple

# Make the project modules importable no matter where the script is started.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config  # noqa: E402

# Below this level (RMS of 16-bit samples) a recording is almost silent.
QUIET_LEVEL = 150


def pick_devices(args, inputs: Sequence[Tuple[int, str]]) -> List[int]:
    """Which device indexes to test, from the command line options.
    --all: every input device. --device N: just N. Otherwise the index from
    config.py (None means the system default, shown as an empty list = default)."""
    if args.all:
        return [index for index, _ in inputs]
    if args.device is not None:
        return [args.device]
    if config.MIC_DEVICE_INDEX is not None:
        return [config.MIC_DEVICE_INDEX]
    return []  # empty = use the system default device


def audio_level(audio) -> Optional[int]:
    """RMS loudness of a recording, or None if it cannot be measured."""
    try:
        import audioop  # removed in Python 3.13, fine on 3.10 to 3.12
        return audioop.rms(audio.frame_data, audio.sample_width)
    except Exception:
        return None


def list_devices() -> List[Tuple[int, str]]:
    """Print every input device and return them as (index, name)."""
    from listener import list_input_devices
    inputs = list_input_devices()
    print("=== Input devices (microphones) ===")
    if not inputs:
        print("NO INPUT DEVICES FOUND. Either PyAudio is not installed")
        print("(pip install pyaudio) or Windows sees no microphone")
        print("(Settings > System > Sound > Input, and Privacy > Microphone).")
        return []
    for index, name in inputs:
        mark = "   <- config.MIC_DEVICE_INDEX" if index == config.MIC_DEVICE_INDEX else ""
        print(f"  [{index}] {name}{mark}")
    if config.MIC_DEVICE_INDEX is None:
        print("  (config.MIC_DEVICE_INDEX is None: the system default device is used)")
    return inputs


def test_device(index: Optional[int], seconds: int = 5) -> str:
    """Record one phrase from one device. Returns "ok", "quiet", "unclear",
    "silent", "offline" or "error"."""
    import speech_recognition as sr

    label = "default device" if index is None else f"device {index}"
    print(f"\n--- Testing {label} ---")
    recognizer = sr.Recognizer()
    try:
        with sr.Microphone(device_index=index) as source:
            print("Stay quiet for 1 second (measuring the room noise)...")
            recognizer.adjust_for_ambient_noise(source, duration=1)
            print(f"Noise threshold: {recognizer.energy_threshold:.0f}")
            print(f"SAY A SHORT SENTENCE NOW ({seconds} seconds)...")
            audio = recognizer.listen(source, timeout=seconds, phrase_time_limit=seconds)
    except sr.WaitTimeoutError:
        print("RESULT: no speech detected. The level is too low, or this is the wrong device.")
        return "silent"
    except (AttributeError, ImportError):
        print("RESULT: PyAudio is missing or broken (pip install pyaudio).")
        return "error"
    except OSError as e:
        print(f"RESULT: cannot open this device ({e}).")
        print("        Often Windows privacy settings block it, or another app uses it.")
        return "error"

    level = audio_level(audio)
    print(f"Recorded. Sound level: {level if level is not None else 'unknown'}")
    try:
        text = recognizer.recognize_google(audio, language=config.STT_LANGUAGE)
    except sr.UnknownValueError:
        if level is not None and level < QUIET_LEVEL:
            print("RESULT: almost silent. Raise the microphone volume in Windows Sound settings.")
            return "quiet"
        print("RESULT: the microphone works, but Google could not understand the words.")
        print("        Speak clearly right after the prompt.")
        return "unclear"
    except sr.RequestError as e:
        print(f"RESULT: audio recorded, but Google is not reachable ({e}). Check your internet.")
        return "offline"
    print(f"RESULT: OK. You said: {text!r}")
    return "ok"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Find the right microphone for Raju.")
    parser.add_argument("--list", action="store_true", help="only list the input devices")
    parser.add_argument("--device", type=int, help="test this device index")
    parser.add_argument("--all", action="store_true", help="test every input device")
    args = parser.parse_args(argv)

    inputs = list_devices()
    if args.list:
        return 0 if inputs else 1

    indexes = pick_devices(args, inputs)
    if args.all and not indexes:
        print("\nNothing to test.")
        return 1
    results = {}
    for index in (indexes or [None]):
        results[index] = test_device(index)

    print("\n=== Summary ===")
    for index, result in results.items():
        label = "default" if index is None else str(index)
        print(f"  device {label}: {result}")
    good = [i for i, r in results.items() if r == "ok"]
    if good:
        print(f"\nUse this in config.py:  MIC_DEVICE_INDEX = {good[0]}")
        print("(or choose the device on the Settings page of the window)")
        return 0
    print("\nNo device understood you. Try --all, raise the microphone volume, "
          "and check the internet.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
