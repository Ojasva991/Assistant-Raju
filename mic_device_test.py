"""
mic_device_test.py
Tests specific microphone device indices one at a time to find which
one actually captures your voice clearly. Run mic_test.py first to see
the full device list, then adjust `candidates` below if needed.

Run:
    py mic_device_test.py
"""

import speech_recognition as sr

recognizer = sr.Recognizer()

# Indices labeled "Microphone" from mic_test.py's device list.
# Edit this list if your device list looks different.
candidates = [1, 5, 9, 19, 20]

for idx in candidates:
    print(f"\n=== Testing device index {idx} ===")
    try:
        with sr.Microphone(device_index=idx) as source:
            recognizer.adjust_for_ambient_noise(source, duration=1)
            print(f"Energy threshold: {recognizer.energy_threshold}")
            print("SAY SOMETHING now (5 sec)...")
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=5)
        text = recognizer.recognize_google(audio, language="en-in")
        print(f"SUCCESS on index {idx}: {text}")
    except sr.WaitTimeoutError:
        print(f"Index {idx}: no sound detected")
    except sr.UnknownValueError:
        print(f"Index {idx}: captured audio but couldn't understand")
    except Exception as e:
        print(f"Index {idx}: error - {e}")
