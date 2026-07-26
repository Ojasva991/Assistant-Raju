"""
features/todo.py
Simple voice-driven to-do list, backed by the SQLite database.
"""


class TodoFeature:
    def __init__(self, memory, voice, listener):
        self.memory = memory
        self.voice = voice
        self.listener = listener

    def add_task(self, user_id=0):
        self.voice.speak("What should I add to your to-do list?")
        task = self.listener.listen()
        if not task:
            self.voice.speak("I didn't catch that. Please try again.")
            return
        self.memory.add_todo(task, user_id=user_id)
        self.voice.speak(f"Added '{task}' to your to-do list.")

    def show_tasks(self, user_id=0):
        tasks = self.memory.get_todos(user_id=user_id)
        if not tasks:
            self.voice.speak("Your to-do list is empty.")
            return
        self.voice.speak(f"You have {len(tasks)} pending tasks.")
        for t in tasks:
            print(f"  [{t['id']}] {t['task']}")
        self.voice.speak("Check the screen for the full list.")

    def complete_task(self, task_id):
        self.memory.complete_todo(task_id)
        self.voice.speak("Marked that task as done.")
