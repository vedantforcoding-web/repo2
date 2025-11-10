"""
VoiceKit Assistant
- GUI: Tkinter with pulsing circle + waveform animation
- Voice: pyttsx3 (male voice)
- Speech recognition: SpeechRecognition (Google)
- Features: Wikipedia & Google search, AI chat (optional OpenAI), open apps by voice
- Add custom app mappings from the GUI
"""

import os
import sys
import threading
import time
import webbrowser
import subprocess
import json
from datetime import datetime
from pathlib import Path
from shutil import which
import traceback

try:
    import tkinter as tk
    from tkinter import messagebox, simpledialog, filedialog
    from PIL import Image, ImageTk
    import pyttsx3
    import speech_recognition as sr
    import wikipedia
except Exception as e:
    print("Missing libraries. Please install: SpeechRecognition, pyttsx3, wikipedia, Pillow, pyaudio")
    print("Error:", e)
    raise

# Optional OpenAI usage (ChatGPT-like). Only used if OPENAI_API_KEY env var is set.
USE_OPENAI = False
if os.getenv("OPENAI_API_KEY"):
    try:
        import openai
        openai.api_key = os.getenv("OPENAI_API_KEY")
        USE_OPENAI = True
    except Exception:
        USE_OPENAI = False

# -------------------- Voice setup --------------------
def setup_voice_engine():
    try:
        engine = pyttsx3.init()
        voices = engine.getProperty("voices")
        # attempt to pick a male voice; fallback to first voice
        male_voice = None
        for v in voices:
            # heuristics: many systems label by name or gender words
            if getattr(v, "name", "").lower().find("male") != -1 or getattr(v, "id", "").lower().find("male") != -1:
                male_voice = v
                break
        if male_voice is None and len(voices) > 0:
            male_voice = voices[0]
        if male_voice:
            engine.setProperty("voice", male_voice.id)
        engine.setProperty("rate", 160)
        return engine
    except Exception as e:
        print("Voice engine init failed:", e)
        return None

engine = setup_voice_engine()

def speak(text):
    """Speak using pyttsx3 safely (non-blocking)."""
    if engine is None:
        print("TTS engine missing. Text:", text)
        return
    try:
        # run in a thread to avoid blocking (pyttsx3 is not fully async-friendly)
        def _say():
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception as ee:
                print("TTS error:", ee)
        threading.Thread(target=_say, daemon=True).start()
    except Exception as e:
        print("Speak error:", e)

# -------------------- Utilities --------------------
def safe_open_url(url):
    try:
        webbrowser.open(url)
        speak("Opening " + url)
    except Exception as e:
        print("Open URL error:", e)
        speak("Sorry, I couldn't open the website.")

def open_app_by_name(name, app_map):
    """
    Try to open app by known mapping or by common commands.
    app_map is a dict of lower-name -> command / exe path
    """
    lname = name.lower().strip()
    # direct mapping from user-configured map
    if lname in app_map:
        cmd = app_map[lname]
        try:
            if os.name == "nt":
                # Windows: start file or exe
                subprocess.Popen(cmd, shell=True)
            else:
                subprocess.Popen(cmd.split(), shell=False)
            speak(f"Opening {name}")
            return True
        except Exception as e:
            print("Open mapped app failed:", e)
            speak(f"Failed to open {name}.")
            return False

    # try built-in shortcuts for common apps
    common_commands = {
        "notepad": "notepad" if os.name == "nt" else "gedit",
        "calculator": "calc" if os.name == "nt" else "gnome-calculator",
        "chrome": "start chrome" if os.name == "nt" else "google-chrome",
        "firefox": "start firefox" if os.name == "nt" else "firefox",
        "vscode": "code" if which("code") else None,
        "explorer": "explorer" if os.name == "nt" else "nautilus",
        "file explorer": "explorer" if os.name == "nt" else "nautilus",
        "spotify": "start spotify" if os.name == "nt" else "spotify",
    }
    if lname in common_commands and common_commands[lname]:
        cmd = common_commands[lname]
        try:
            subprocess.Popen(cmd, shell=True)
            speak(f"Opening {name}")
            return True
        except Exception as e:
            print("Open common app failed:", e)

    # search PATH for executable with the name
    if which(lname):
        try:
            subprocess.Popen([lname])
            speak(f"Opening {name}")
            return True
        except Exception as e:
            print("Open PATH app failed:", e)

    # fallback: try to find .exe in Program Files (Windows)
    if os.name == "nt":
        possible = []
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        for root in (pf, pf86):
            if root and os.path.exists(root):
                for p in Path(root).rglob("*.exe"):
                    if p.stem.lower() == lname:
                        possible.append(str(p))
                        break
        if possible:
            try:
                subprocess.Popen(possible[0], shell=True)
                speak(f"Opening {name}")
                return True
            except Exception as e:
                print("Open exe found failed:", e)

    speak(f"Sorry, I can't find an app called {name}. You can add it from the UI.")
    return False

# -------------------- Speech Listening --------------------
recognizer = sr.Recognizer()

def listen_once(timeout=6, phrase_time_limit=8):
    """
    Returns recognized text or None.
    Uses Google Web Speech API (requires internet).
    """
    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.6)
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        text = recognizer.recognize_google(audio)
        print("Recognized:", text)
        return text
    except sr.WaitTimeoutError:
        print("Timeout waiting for speech.")
        return None
    except sr.UnknownValueError:
        print("Could not understand audio.")
        return None
    except sr.RequestError as e:
        print("Could not request results; network error:", e)
        return None
    except Exception as e:
        print("General listen error:", e)
        return None

# -------------------- AI chat (light) --------------------
def ai_chat_local(prompt):
    """
    Small rule-based fallback chat. If USE_OPENAI True, call OpenAI API instead.
    """
    if USE_OPENAI:
        try:
            # simple completion call (you can tune model and params)
            resp = openai.Completion.create(
                model="text-davinci-003",
                prompt=prompt,
                max_tokens=150,
                temperature=0.6,
            )
            return resp.choices[0].text.strip()
        except Exception as e:
            print("OpenAI error:", e)
            # fall back to local
    # Local simple responses
    lp = prompt.lower()
    if "how are you" in lp:
        return "I'm fine, thanks. I'm here to help you with coding, apps, and questions."
    if "your name" in lp:
        return "My name is VoiceKit."
    if "joke" in lp or "funny" in lp:
        return "Why do programmers prefer dark mode? Because light attracts bugs!"
    if "help" in lp or "how" in lp:
        return "Tell me what you want: open an app, search something, or chat with me."
    return "That's interesting. I can search Wikipedia or Google for detailed answers."

# -------------------- Persisted app mappings --------------------
APP_MAP_FILE = Path.home() / ".voicekit_appmap.json"

def load_app_map():
    if APP_MAP_FILE.exists():
        try:
            return json.loads(APP_MAP_FILE.read_text())
        except Exception:
            return {}
    return {}

def save_app_map(mapping):
    try:
        APP_MAP_FILE.write_text(json.dumps(mapping, indent=2))
    except Exception as e:
        print("Save app map failed:", e)

# -------------------- GUI --------------------
class VoiceKitApp:
    def __init__(self, root):
        self.root = root
        self.root.title("VoiceKit Assistant")
        self.root.geometry("520x620")
        self.root.configure(bg="#0f0f11")
        self.app_map = load_app_map()

        # Title
        tk.Label(root, text="VoiceKit Assistant", font=("Segoe UI", 20, "bold"),
                 bg="#0f0f11", fg="#e6eef8").pack(pady=12)

        # Canvas container
        self.canvas = tk.Canvas(root, width=300, height=300, bg="#0f0f11", highlightthickness=0)
        self.canvas.pack(pady=6)
        self.circle = self.canvas.create_oval(90, 90, 210, 210, fill="#3aa0ff", outline="")
        # waveform lines
        self.waves = [self.canvas.create_line(40+i*12, 260, 40+i*12, 260, fill="#7be1ff", width=3) for i in range(14)]

        # Buttons row
        btn_frame = tk.Frame(root, bg="#0f0f11")
        btn_frame.pack(pady=10)
        self.listen_btn = tk.Button(btn_frame, text="🎙️ Listen (Voice)", command=self.voice_listen,
                                    bg="#2ea1ff", fg="white", font=("Segoe UI", 11), padx=12, pady=8, bd=0)
        self.listen_btn.grid(row=0, column=0, padx=8)

        self.type_btn = tk.Button(btn_frame, text="⌨️ Type & Send", command=self.type_and_send,
                                  bg="#17a589", fg="white", font=("Segoe UI", 11), padx=12, pady=8, bd=0)
        self.type_btn.grid(row=0, column=1, padx=8)

        self.add_app_btn = tk.Button(btn_frame, text="➕ Add App", command=self.add_app_dialog,
                                     bg="#ffa726", fg="white", font=("Segoe UI", 11), padx=12, pady=8, bd=0)
        self.add_app_btn.grid(row=0, column=2, padx=8)

        # Text entry for typed commands
        self.entry = tk.Entry(root, font=("Segoe UI", 12), width=44, bg="#1b1b1b", fg="white", insertbackground="white")
        self.entry.pack(pady=8)

        # Output area
        self.output = tk.Text(root, height=8, bg="#101010", fg="#c7f9e3", font=("Segoe UI", 11), wrap="word")
        self.output.pack(padx=12, pady=10, fill="x")
        self.output.insert("end", "Say commands like: 'open chrome', 'wikipedia alan turing', 'search python list', 'play music', 'chat how are you'\n")
        self.output.configure(state="disabled")

        # Status
        self.status_var = tk.StringVar(value="Ready")
        tk.Label(root, textvariable=self.status_var, bg="#0f0f11", fg="#9fd3ff", font=("Segoe UI", 10)).pack(pady=6)

        # animation control
        self.animating = False

    # ---------------- Animation ----------------
    def start_animation(self):
        if self.animating:
            return
        self.animating = True
        threading.Thread(target=self._animate_loop, daemon=True).start()

    def stop_animation(self):
        self.animating = False

    def _animate_loop(self):
        grow = True
        t = 0.0
        while self.animating:
            try:
                # pulse circle
                coords = self.canvas.coords(self.circle)
                cx = (coords[0] + coords[2]) / 2
                cy = (coords[1] + coords[3]) / 2
                factor = 1.01 if grow else 0.99
                self.canvas.scale(self.circle, cx, cy, factor, factor)

                # waveform simulation
                for i, line_id in enumerate(self.waves):
                    h = 20 + (1 + (0.5 + 0.5 * (1 + (0.5 * (i%3)))) ) * (10 * abs((i * 0.3 + t) % 3 - 1.5))
                    x = 40 + i * 12
                    self.canvas.coords(line_id, x, 260 - h, x, 260)
                t += 0.12

                # flip grow when too large/small
                coords = self.canvas.coords(self.circle)
                width = coords[2] - coords[0]
                if width > 150:
                    grow = False
                elif width < 100:
                    grow = True

                time.sleep(0.04)
            except Exception:
                break

    # ---------------- UI helpers ----------------
    def log(self, text):
        self.output.configure(state="normal")
        self.output.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {text}\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def set_status(self, text):
        self.status_var.set(text)

    # ---------------- Commands ----------------
    def handle_command_text(self, command):
        """Process a typed or recognized command string."""
        command = (command or "").strip()
        if not command:
            return

        self.log("Command: " + command)
        cmd = command.lower()

        # simple patterns
        if cmd.startswith("open "):
            app_name = cmd.replace("open ", "", 1).strip()
            self.set_status("Opening app: " + app_name)
            open_app_by_name(app_name, self.app_map)
            return

        if cmd.startswith("search "):
            topic = command.replace("search ", "", 1).strip()
            self.set_status("Searching web: " + topic)
            safe_open_url(f"https://www.google.com/search?q={webbrowser.quote(topic) if hasattr(webbrowser, 'quote') else topic}")
            return

        if cmd.startswith("wikipedia "):
            topic = command.replace("wikipedia ", "", 1).strip()
            self.set_status("Searching Wikipedia: " + topic)
            threading.Thread(target=self._wikipedia_search, args=(topic,), daemon=True).start()
            return

        if cmd.startswith("play music"):
            # open Music folder
            music_dir = os.path.expanduser("~/Music")
            if os.path.exists(music_dir):
                try:
                    os.startfile(music_dir) if os.name == "nt" else subprocess.Popen(["xdg-open", music_dir])
                    speak("Opening your Music folder")
                except Exception as e:
                    print("Play music error:", e)
                    speak("Couldn't open the music folder.")
            else:
                speak("Music folder not found.")
            return

        if "time" in cmd and len(cmd.split()) <= 3:
            speak(f"The time is {datetime.now().strftime('%I:%M %p')}")
            return

        if cmd.startswith("chat ") or cmd.startswith("talk "):
            prompt = command.split(" ", 1)[1] if " " in command else ""
            self.set_status("Chatting...")
            threading.Thread(target=self._chat_with_ai, args=(prompt,), daemon=True).start()
            return

        # fallback: try ai chat
        self.set_status("Thinking...")
        threading.Thread(target=self._chat_with_ai, args=(command,), daemon=True).start()

    def _wikipedia_search(self, topic):
        try:
            self.log("Wikipedia search for: " + topic)
            summary = wikipedia.summary(topic, sentences=2)
            self.log("Wikipedia: " + summary)
            speak(summary)
        except Exception as e:
            print("Wiki error:", e)
            speak("I couldn't find that on Wikipedia.")
        finally:
            self.set_status("Ready")

    def _chat_with_ai(self, prompt):
        try:
            self.log("AI prompt: " + prompt)
            answer = ai_chat_local(prompt)
            self.log("AI answer: " + answer)
            speak(answer)
        except Exception as e:
            print("AI chat error:", e)
            speak("I couldn't complete the chat request.")
        finally:
            self.set_status("Ready")

    # ---------------- Voice & Type entry actions ----------------
    def voice_listen(self):
        """Start voice capture in background, animate while listening."""
        self.set_status("Listening...")
        self.log("Listening (voice)...")
        self.start_animation()
        threading.Thread(target=self._do_voice_listen, daemon=True).start()

    def _do_voice_listen(self):
        try:
            txt = listen_once()
            self.stop_animation()
            self.canvas.coords(self.circle, 90, 90, 210, 210)
            if txt:
                self.entry.delete(0, "end")
                self.entry.insert(0, txt)
                self.handle_command_text(txt)
            else:
                speak("I didn't catch that. Try again.")
                self.log("No speech recognized.")
            self.set_status("Ready")
        except Exception as e:
            print("Voice listen error:", e)
            traceback.print_exc()
            self.set_status("Ready")
            self.stop_animation()

    def type_and_send(self):
        text = self.entry.get().strip()
        if not text:
            speak("Please type a command first.")
            return
        self.handle_command_text(text)

    # ---------------- App mapping UI ----------------
    def add_app_dialog(self):
        name = simpledialog.askstring("Add App", "What name will you say to open this app? (e.g. 'chrome')", parent=self.root)
        if not name:
            return
        path = filedialog.askopenfilename(title=f"Select executable for {name}")
        if not path:
            return
        # store mapping (use quoted path if spaces)
        self.app_map[name.lower().strip()] = f'"{path}"' if " " in path else path
        save_app_map(self.app_map)
        speak(f"Saved mapping for {name}")
        self.log(f"Added app mapping: {name} -> {path}")

# -------------------- Main --------------------
def main():
    root = tk.Tk()
    app = VoiceKitApp(root)
    # greet user
    speak("Hello! VoiceKit is ready. Say: open chrome, search python list, wikipedia alan turing, or chat tell me a joke.")
    root.mainloop()

if __name__ == "__main__":
    main()
