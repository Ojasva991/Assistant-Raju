"""
main.py
Entry point. Run this file to start J:

    python main.py

If you don't have a microphone set up or just want to test without
speaking, run with typed input instead:

    python main.py --text
"""

import sys
import traceback

import config
from assistant import J


def main():
    use_microphone = "--text" not in sys.argv

    j = J(use_microphone=use_microphone)
    j.greet()
    if use_microphone:
        print(f'[main] Say "{config.WAKE_WORD}" before each command to wake {config.ASSISTANT_NAME} up.')

    while True:
        try:
            if use_microphone:
                command = j.listen_for_command()   # waits for "hey j" first
            else:
                command = j.listener.listen()      # typed input, no wake word needed
            if command:
                j.execute(command)
        except SystemExit:
            break
        except Exception:
            # Don't let one bad command crash the whole assistant
            print("[main] Something went wrong, continuing...")
            traceback.print_exc()


if __name__ == "__main__":
    main()
