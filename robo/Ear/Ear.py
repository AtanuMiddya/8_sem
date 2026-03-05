# ear.py

# Standard library imports
import os
import threading
import time
from queue import Queue
import json

# Third-party imports
import speech_recognition as sr
import requests # Use requests library for direct API calls

# --- Gemini API Configuration ---
# IMPORTANT: Paste your secret API key into the line below.
# WARNING: For security, it is strongly recommended to use environment variables
# instead of pasting your key directly in the code. Do NOT share this file
# with your key pasted in it.

GEMINI_API_KEY = "AIzaSyC-SF3WYTgZRl-YZAC2d6Qls0HsWjMAMAc"

# --- Code Initialization ---
# This block checks if the API key has been added.
if not GEMINI_API_KEY or GEMINI_API_KEY == "PASTE_YOUR_API_KEY_HERE":
    print("FATAL ERROR: The 'GEMINI_API_KEY' variable is not set in the script.")
    print("Please open ear.py and paste your API key into the designated variable.")
    exit()


class Ear:
    """
    The "Ear" of the robot. This class runs in a separate thread,
    constantly listening for a wake word and a command. It uses
    Gemini to interpret and correct the recognized command before
    passing it to the master controller via a shared queue.
    """
    def __init__(self, command_queue):
        """
        Initializes the Ear.
        :param command_queue: A thread-safe queue to pass commands back to the main script.
        """
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.command_queue = command_queue
        self.is_listening = False
        self.listener_thread = None
        self.wake_word = "arm"

        # This system instruction gives Gemini its role and context for text correction.
        self.system_instruction = (
            "You are an AI assistant for a robot arm's voice control system. "
            "Your task is to interpret transcribed voice commands that may contain speech recognition errors. "
            "Correct and clarify the command based on common robotic arm actions (e.g., 'open gripper', "
            "'close gripper', 'raise elbow', 'lower wrist', 'rotate base', 'move forward'). "
            "Keep the command concise and direct. If the command is unintelligible or not a robot command, "
            "respond with only the word 'unintelligible'. Do not add any conversational filler or explanations. "
            "For example, if the input is 'lower the el', you must output 'lower the elbow'."
        )
        print("Ear: Ready to interpret commands.")


    def _interpret_command_with_gemini(self, raw_text):
        """
        Sends the raw, transcribed text to Gemini via a direct REST API call for interpretation.
        :param raw_text: The string captured by the speech recognizer.
        :return: A cleaned and interpreted command string, or the original text on failure.
        """
        print("Sending to Gemini for interpretation...")

        # Using the stable 'gemini-pro' model endpoint.
        api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent"
        headers = {
            'Content-Type': 'application/json',
            'x-goog-api-key': GEMINI_API_KEY
        }
        
        # Construct the payload for a text-only response
        payload = {
            "contents": [{"parts": [{"text": raw_text}]}],
            "systemInstruction": {"parts": [{"text": self.system_instruction}]},
            "generationConfig": {"temperature": 0.2}
        }

        try:
            response = requests.post(api_url, headers=headers, json=payload, timeout=10)
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
            
            result = response.json()
            
            # Safely extract the text from the response
            candidate = result.get('candidates', [{}])[0]
            content_part = candidate.get('content', {}).get('parts', [{}])[0]
            interpreted_command = content_part.get('text', '').strip().lower()

            if not interpreted_command or "unintelligible" in interpreted_command:
                print("  -> Gemini found the command unintelligible.")
                return None

            print(f"  -> Gemini's interpretation: '{interpreted_command}'")
            return interpreted_command

        except requests.exceptions.RequestException as e:
            print(f"  -> ERROR: Could not call Gemini API: {e}")
            print("  -> Fallback: Using the original recognized text.")
            return raw_text
        except (KeyError, IndexError) as e:
            print(f"  -> ERROR: Could not parse Gemini's response: {e}")
            print(f"  -> Raw response: {result}")
            return raw_text


    def _listener_thread_loop(self):
        """
        The main loop for the background listening thread.
        """
        while self.is_listening:
            print(f"\nListening for a command (e.g., '{self.wake_word} open the gripper')...")
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                try:
                    audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=5)
                except sr.WaitTimeoutError:
                    continue # Loop again if no sound is detected

            try:
                print("Recognizing speech...")
                text = self.recognizer.recognize_google(audio).lower()
                print(f"  -> Heard: '{text}'")

                if self.wake_word in text:
                    raw_command = text.replace(self.wake_word, "", 1).strip()
                    print(f"  -> Command extracted: '{raw_command}'")

                    if raw_command:
                        final_command = self._interpret_command_with_gemini(raw_command)

                        if final_command:
                            if 'exit' in final_command or 'shutdown' in final_command:
                                self.command_queue.put('exit')
                                break

                            while not self.command_queue.empty():
                                try: self.command_queue.get_nowait()
                                except Queue.empty: pass
                            self.command_queue.put( final_command)

            except (sr.RequestError, sr.UnknownValueError):
                # Ignore network errors or unintelligible speech
                continue

        print("Ear: Listener thread has stopped.")

    def start(self):
        """Starts the background listening thread."""
        if self.is_listening:
            print("Ear is already listening.")
            return

        self.is_listening = True
        self.listener_thread = threading.Thread(target=self._listener_thread_loop, daemon=True)
        self.listener_thread.start()
        print("Ear is online.")

    def stop(self):
        """Stops the background listening thread."""
        print("Ear is shutting down...")
        self.is_listening = False
        if self.listener_thread:
            self.listener_thread.join()
        print("Ear has been shut down.")

# --- Main Execution Block for Standalone Testing ---
if __name__ == "__main__":
    print("--- Ear Standalone Test Mode ---")
    test_queue = Queue()
    
    # Instantiate the Ear; it no longer needs a model name passed to it.
    ear_test = Ear(test_queue)
    ear_test.start()
    
    print("\nSpeak a command starting with the wake word 'arm'. Say 'arm exit' to stop.")

    try:
        while True:
            if not test_queue.empty():
                command = test_queue.get()
                print(f"\n[Test Script] Received FINAL command from Ear: '{command}'")
                if command == 'exit':
                    break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping test...")
            
    ear_test.stop()
    print("Test finished.")

