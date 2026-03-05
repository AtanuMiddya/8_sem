import serial
import time
import json
import requests  # Use the 'requests' library for standard Python HTTP calls
from serial.tools import list_ports # Used to help find the correct COM port

class ArmController:
    """
    A class to control the 6-axis robotic arm using natural language commands
    processed by the Gemini API.
    """
    def __init__(self, port="COM7", baud_rate=115200):
        """Initializes the connection to the Arduino and loads arm configuration."""
        self.ARDUINO_PORT = port
        self.BAUD_RATE = baud_rate
        self.arduino = None
        self.current_angles = self._get_previous_state()

        # This configuration is crucial for Gemini to understand the arm's limits.
        self.SERVO_CONFIG = {
            "Base":      {"min": 0, "max": 180, "index": 0, "current": self.current_angles[0]},
            "Shoulder":  {"min": 0, "max": 170, "index": 1, "current": self.current_angles[1]},
            "Elbow":     {"min": 56, "max": 108, "index": 2, "current": self.current_angles[2]},
            "Wrist":     {"min": 15, "max": 180, "index": 3, "current": self.current_angles[3]},
            "WristRoll": {"min": 0, "max": 166, "index": 4, "current": self.current_angles[4]},
            "Gripper":   {"min": 0, "max": 85,  "index": 5, "current": self.current_angles[5]}
        }

    def connect(self):
        """Establishes the serial connection to the Arduino."""
        try:
            self.arduino = serial.Serial(self.ARDUINO_PORT, self.BAUD_RATE, timeout=2)
            time.sleep(2)
            print(f"Successfully connected to Arduino on {self.ARDUINO_PORT}")
            return True
        except serial.SerialException as e:
            print(f"Error connecting to Arduino on {self.ARDUINO_PORT}: {e}")
            print("Please check the port and your connection.")
            available_ports = list(list_ports.comports())
            if available_ports:
                print("Available COM ports:")
                for p in available_ports:
                    print(f"  - {p.device}")
            else:
                print("No COM ports found.")
            return False

    def disconnect(self):
        """Closes the serial connection."""
        if self.arduino and self.arduino.is_open:
            self.arduino.close()
            print("Serial port closed.")

    def _get_previous_state(self):
        """Reads the last saved set of angles from the text file."""
        try:
            with open("prev_teta.txt", "r") as text_file:
                prev_teta_string = text_file.read()
                prev_teta = [int(float(i)) for i in prev_teta_string.strip().split(";") if i]
                return prev_teta
        except FileNotFoundError:
            print("Warning: prev_teta.txt not found. Using default home angles.")
            return [90, 85, 140, 150, 35, 90] # Home position from your notes

    def _write_arduino(self, angles):
        """Formats the full angle list and sends it to the Arduino."""
        if not self.arduino or not self.arduino.is_open:
            print("Error: Arduino not connected.")
            return
            
        self.current_angles = angles.copy() # Update internal state
        
        angles_to_send = angles.copy()
        angles_to_send[0] = 180 - angles_to_send[0] # Invert Base
        angles_to_send[3] = 180 - angles_to_send[3] # Invert Wrist

        angle_string = ','.join([str(int(elem)) for elem in angles_to_send])
        final_command = f"P{angle_string},200\n"
        
        self.arduino.write(final_command.encode('utf-8'))
        
        with open("prev_teta.txt", "w") as text_file:
            text_file.write(";".join(map(str, self.current_angles)) + ";")

    def get_angles_from_gemini(self, command):
        """
        Sends a command to the Gemini API and gets a structured JSON response.
        """
        print("\nAsking Gemini for motor angles...")
        
        system_instruction = f"""
        You are an expert roboticist controlling a 6-axis robotic arm. 
        Your sole purpose is to convert a user's natural language command into a precise JSON object 
        representing the target angles for each of the arm's six servos.
        You must adhere to the physical constraints of each servo. 
        Never generate an angle outside of the specified [min, max] safe zone.

        Here are the servos, their safe zones, and their current angles:
        - Base: [min: {self.SERVO_CONFIG['Base']['min']}, max: {self.SERVO_CONFIG['Base']['max']}], current: {self.current_angles[0]}
        - Shoulder: [min: {self.SERVO_CONFIG['Shoulder']['min']}, max: {self.SERVO_CONFIG['Shoulder']['max']}], current: {self.current_angles[1]}
        - Elbow: [min: {self.SERVO_CONFIG['Elbow']['min']}, max: {self.SERVO_CONFIG['Elbow']['max']}], current: {self.current_angles[2]}
        - Wrist: [min: {self.SERVO_CONFIG['Wrist']['min']}, max: {self.SERVO_CONFIG['Wrist']['max']}], current: {self.current_angles[3]}
        - WristRoll: [min: {self.SERVO_CONFIG['WristRoll']['min']}, max: {self.SERVO_CONFIG['WristRoll']['max']}], current: {self.current_angles[4]}
        - Gripper: [min: {self.SERVO_CONFIG['Gripper']['min']}, max: {self.SERVO_CONFIG['Gripper']['max']}], current: {self.current_angles[5]} (0=closed, 85=open)

        Analyze the user's command and determine the most appropriate angle for EACH servo.
        You MUST return a value for every servo. If a servo is not mentioned, return its current angle.
        """

        response_schema = {"type": "OBJECT", "properties": { "base": {"type": "INTEGER"}, "shoulder": {"type": "INTEGER"}, "elbow": {"type": "INTEGER"}, "wrist": {"type": "INTEGER"}, "wrist_roll": {"type": "INTEGER"}, "gripper": {"type": "INTEGER"},}, "required": ["base", "shoulder", "elbow", "wrist", "wrist_roll", "gripper"]}

        api_key = "AIzaSyAMkGJSvTZ2DnoVk5amcImZ_51yHF2qOdc" # The execution environment provides the key.
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={api_key}"

        payload = {"contents": [{"parts": [{"text": command}]}],"systemInstruction": {"parts": [{"text": system_instruction}]},"generationConfig": {"responseMimeType": "application/json","responseSchema": response_schema}}

        try:
            response = requests.post(api_url, json=payload)
            response.raise_for_status() # Raise an exception for bad status codes
            result = response.json()
            
            json_text = result['candidates'][0]['content']['parts'][0]['text']
            return json.loads(json_text)
        except requests.exceptions.RequestException as e:
            print(f"Error calling Gemini API: {e}")
            return None
        except (KeyError, IndexError) as e:
            print(f"Error parsing Gemini response: {e}")
            print(f"Full response: {result}")
            return None


    def execute_command(self, command):
        """Processes a natural language command and moves the arm."""
        angles_dict = self.get_angles_from_gemini(command)
        
        if angles_dict:
            print(f"Gemini response received: {angles_dict}")
            
            final_angles = [
                angles_dict.get('base', self.current_angles[0]),
                angles_dict.get('shoulder', self.current_angles[1]),
                angles_dict.get('elbow', self.current_angles[2]),
                angles_dict.get('wrist', self.current_angles[3]),
                angles_dict.get('wrist_roll', self.current_angles[4]),
                angles_dict.get('gripper', self.current_angles[5])
            ]
            
            print(f"Executing move to: {final_angles}")
            self._write_arduino(final_angles)
            return True
        else:
            print("Could not execute command.")
            return False

# --- Main Execution Block ---
def main():
    """Runs the interactive command loop for the arm controller."""
    arm = ArmController()
    if arm.connect():
        print("\n--- Gemini Arm Controller Initialized ---")
        print("Enter a command for the arm, or type 'exit' to quit.")
        
        while True:
            command = input("command> ")
            if command.lower() == 'exit':
                break
            arm.execute_command(command)
            
        arm.disconnect()

if __name__ == "__main__":
    # This script now runs in a standard Python environment.
    # Make sure you have the required libraries:
    # pip install pyserial requests
    main()

