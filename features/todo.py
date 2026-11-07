"""
features/todo.py
Simple voice-driven to-do list, backed by the SQLite database.
"""


from listener import hear_answer

SPOKEN_ITEMS = 3   # how many items "show my tasks" reads aloud


class TodoFeature:
    def __init__(self, memory, voice, listener):
        self.memory = memory
        self.voice = voice
        self.listener = listener

    def add_task(self, user_id=0):
        self.voice.speak("What should I add to your to-do list?")
        task = hear_answer(self.listener)
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
        count = len(tasks)
        self.voice.speak(f"You have {count} pending task{'s' if count != 1 else ''}.")
        # Read only the first few aloud: a long list is tiring to listen to.
        first = tasks[:SPOKEN_ITEMS]
        self.voice.speak("; ".join(t["task"] for t in first) + ".")
        if count > len(first):
            self.voice.speak("The full list is on the Tasks page.")

    def complete_task(self, task_id):
        self.memory.complete_todo(task_id)
        self.voice.speak("Marked that task as done.")
