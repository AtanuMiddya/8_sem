import speech_recognition as sr
import requests
import json

def listen_for_audio(recognizer, microphone, prompt):
    """
    A helper function to capture audio from the microphone, display a prompt,
    and convert the audio to text.
    """
    with microphone as source:
        print(prompt)
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        audio = recognizer.listen(source)

    try:
        print("Recognizing speech...")
        text = recognizer.recognize_google(audio)
        print(f"  -> Heard: '{text}'")
        return text.lower()
    except sr.RequestError:
        print("API unavailable. Check your internet connection.")
    except sr.UnknownValueError:
        # This is common when no speech is detected, so we can ignore the error message
        pass
    return None

def get_gemini_interpretation(raw_text):
    """
    Sends the raw text to the Gemini API to be corrected and clarified.
    """
    print("Sending to Gemini for interpretation...")

    # The system instruction tells Gemini its role: to act as a command corrector.
    system_instruction = """
    You are an AI assistant that cleans up and corrects transcribed voice commands for a robotic arm.
    The user's input is raw text from a speech-to-text engine and may contain errors.
    Your task is to analyze the text, fix any speech recognition mistakes, and output the clear, intended command.
    For example, if the input is 'lift the bolder up', you should output 'lift the shoulder up'.
    If the command is clear, return it as is.
    Your response must only be the corrected command text and nothing else.
    """

    # --- API KEY & URL ---
    api_key = "AIzaSyC-SF3WYTgZRl-YZAC2d6Qls0HsWjMAMAc"
    # The API key will now be sent in the headers, not the URL itself.
    api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent"

    payload = {
        "contents": [{"parts": [{"text": raw_text}]}],
        "systemInstruction": {"parts": [{"text": system_instruction}]}
    }

    # A more robust way to send the API key is through the request headers.
    headers = {
        'Content-Type': 'application/json',
        'x-goog-api-key': api_key
    }

    try:
        # Pass the headers dictionary to the request call
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status() # Raise an error for bad responses (4xx or 5xx)
        result = response.json()

        # Extract the corrected text from Gemini's response
        interpreted_text = result['candidates'][0]['content']['parts'][0]['text']
        print(f"  -> Gemini's interpretation: '{interpreted_text}'")
        return interpreted_text
    except requests.exceptions.RequestException as e:
        print(f"Error calling Gemini API: {e}")
    except (KeyError, IndexError):
        print("Error parsing Gemini's response.")
        print(f"Full response: {result}")
    return None

def main():
    """Main loop to listen for a wake word, then a command."""
    recognizer = sr.Recognizer()
    microphone = sr.Microphone()
    wake_word = "arm"

    print("--- Voice Command Accuracy Test ---")
    print(f"Say '{wake_word}' followed by a command, or say 'exit' to quit.")

    while True:
        # Listen for a full phrase
        print(f"\nListening for a command (e.g., '{wake_word} open the gripper')...")
        text = listen_for_audio(recognizer, microphone, prompt="")

        if text:
            # Check if the wake word is in the recognized text
            if wake_word in text:
                # Extract the actual command part of the text
                command = text.replace(wake_word, "", 1).strip()
                
                if command:
                    print(f"  -> Command extracted: '{command}'")
                    # Get Gemini's improved version of the command
                    get_gemini_interpretation(command)
                else:
                    print("Heard the wake word, but no command followed. Please try again.")

            elif 'exit' in text:
                print("Exiting test.")
                break

if __name__ == "__main__":
    # Ensure you have the necessary libraries installed:
    # pip install SpeechRecognition PyAudio requests
    main()

