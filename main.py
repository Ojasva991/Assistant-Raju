"""
main.py
Entry point. Run this file to start Raju:

    python main.py

If you don't have a microphone set up or just want to test without
speaking, run with typed input instead:

    python main.py --text
"""

import sys
import traceback

import config
from assistant import Assistant


def main():
    use_microphone = "--text" not in sys.argv

    j = Assistant(use_microphone=use_microphone)
    j.greet()
    if use_microphone:
        print(f'[main] Say "{config.WAKE_WORD}" before each command to wake {config.ASSISTANT_NAME} up.')

    window_was_open = False
    while True:
        try:
            if use_microphone:
                command = j.listen_for_command()   # waits for the wake word first
            else:
                command = j.listener.listen()      # typed input, no wake word needed
            if not command and window_was_open and not j.follow_up_seconds_left():
                print(f'[main] Wake word needed again: say "{config.WAKE_WORD}" first.')
                window_was_open = False
            if command:
                print(f"You: {command}")  # the listener no longer prints what it heard
                j.execute(command)
                if use_microphone and j.follow_up_seconds_left():
                    window_was_open = True
                    print(f"[main] No wake word needed for the next "
                          f"{config.FOLLOW_UP_SECONDS} seconds.")
        except SystemExit:
            break
        except Exception:
            # Don't let one bad command crash the whole assistant
            print("[main] Something went wrong, continuing...")
            traceback.print_exc()


if __name__ == "__main__":
    main()
