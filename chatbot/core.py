"""
core.py - Core chatbot logic and extensibility interface
"""
import importlib
import os

class Chatbot:
    def __init__(self, persona=None):
        self.persona = persona or "You are a helpful threat assessor chatbot."
        self.modules = self.load_modules()
        self.history = []

    def load_modules(self):
        modules = []
        modules_dir = os.path.join(os.path.dirname(__file__), "modules")
        if os.path.isdir(modules_dir):
            for fname in os.listdir(modules_dir):
                if fname.endswith(".py") and fname != "__init__.py":
                    mod_name = f"chatbot.modules.{fname[:-3]}"
                    try:
                        mod = importlib.import_module(mod_name)
                        if hasattr(mod, "process"):
                            modules.append(mod)
                    except Exception as e:
                        print(f"Module load error: {mod_name}: {e}")
        return modules

    def respond(self, user_input):
        self.history.append({"user": user_input})
        # Route to modules if available
        for mod in self.modules:
            try:
                result = mod.process(user_input, self.history, self.persona)
                if result:
                    self.history.append({"bot": result})
                    return result
            except Exception as e:
                print(f"Module error: {mod.__name__}: {e}")
        # Default echo response
        response = f"[Threat Assessor] You said: '{user_input}'"
        self.history.append({"bot": response})
        return response
