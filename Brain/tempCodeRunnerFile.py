import time
import requests
import json
# CORRECTED: This relative import works correctly when called from Master.py
from . import solverNNA as ik_solver
from .nervousSystem import NervousSystem

class Brain:
    """
    The "Cerebrum" of the robot. This is the high-level planner.
    It understands abstract goals, plans multi-step action sequences,
    uses the IK solver to calculate movements, and sends simple commands
    to the NervousSystem. It has no direct connection to the hardware.
    """
    def __init__(self, nervous_system: NervousSystem):
        """
        Initializes the Brain.
        :param nervous_system: An instance of the NervousSystem class.
        """
        self.nervous_system = nervous_system
        self.api_key = "PASTE_YOUR_GEMINI_API_KEY_HERE" # IMPORTANT

        # --- Memory and State ---
        self.object_in_gripper = None # Remembers what it's holding
        self.defining_point_name = None # State for when we are defining a point (e.g., 'A', 'B')
        self.drop_points = {} # Stores the coordinates of defined points, like {'A': (x, y, z)}
        
        # --- Predefined Positions and Heights (in mm) ---
        self.safe_height = 150 # A safe Z-height for moving above objects
        self.pickup_approach_height = 50 # Height to approach an object before grabbing

    def _interpret_with_gemini(self, command, detections):
        """
        New role for Gemini: Understand user intent, target object, OR if a point is being defined.
        """
        detected_object_names = list(set([d['name'] for d in detections]))
        
        system_instruction = f"""
        You are an expert roboticist parsing a user's command. Your job is to determine the user's INTENT 
        and any associated TARGET. The user sees a camera feed with these objects: {detected_object_names}.

        There are three possible intents: "pickup", "place", and "define_point".

        1. If the user wants to pick up an object, the intent is "pickup" and the target is the object's name.
           The target MUST be one of the objects from the detected list.
        2. If the user wants to place an object, the intent is "place". The target should be the name of a drop point (e.g., "A", "B").
        3. If the user wants to define a location (e.g., "define point A", "this is point B"), the intent is "define_point" 
           and the target is the name of the point (e.g., "A", "B").

        Respond with a JSON object with two keys: "intent" and "target". 
        If no specific target is mentioned for a valid intent, the target can be null.
        If the command is unintelligible, return intent as null.
        
        Example 1:
        Command: "arm pick up the bottle"
        Response: {{"intent": "pickup", "target": "bottle"}}
        
        Example 2:
        Command: "now place it at point a"
        Response: {{"intent": "place", "target": "A"}}

        Example 3:
        Command: "let's define point a"
        Response: {{"intent": "define_point", "target": "A"}}
        """
        
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={self.api_key}"
        headers = {'Content-Type': 'application/json'}
        payload = {"contents": [{"parts": [{"text": command}]}], "systemInstruction": {"parts": [{"text": system_instruction}]}}

        try:
            response = requests.post(api_url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            json_text = result['candidates'][0]['content']['parts'][0]['text']
            clean_json_text = json_text.strip().replace("```json", "").replace("```", "")
            return json.loads(clean_json_text)
        except Exception as e:
            print(f"Brain Error: Could not get interpretation from Gemini API. {e}")
            return {"intent": None, "target": None}

    def _calculate_ik_solution(self, x, y, z):
        """
        Calculates the full 6-servo angle solution for a target coordinate.
        """
        base_angles = ik_solver.move_to_position_cart(x, y, z)
        current_state = self.nervous_system._get_current_state()
        wrist_roll = current_state[4]
        gripper = current_state[5]
        return base_angles + [wrist_roll, gripper]

    def _find_target_coords(self, target_name, detections):
        """Finds the real-world XYZ coordinates of a detected object."""
        for detection in detections:
            if detection['name'] == target_name:
                return (detection['world_x'], detection['world_y'], detection['world_z'])
        return None

    def _execute_pickup_sequence(self, target_name, target_coords):
        """Executes the multi-step sequence to pick up an object."""
        print(f"Brain: Initiating pickup sequence for '{target_name}' at {target_coords}.")
        x, y, z = target_coords
        angles_above = self._calculate_ik_solution(x, y, self.safe_height)
        self.nervous_system.move_to_angles(angles_above, speed=400)
        time.sleep(2)
        self.nervous_system.set_gripper("open")
        time.sleep(1)
        angles_approach = self._calculate_ik_solution(x, y, self.pickup_approach_height)
        self.nervous_system.move_to_angles(angles_approach, speed=200)
        time.sleep(2)
        self.nervous_system.set_gripper("closed")
        time.sleep(1)
        self.nervous_system.move_to_angles(angles_above, speed=200)
        time.sleep(2)
        self.object_in_gripper = target_name
        print(f"Brain: Successfully picked up '{self.object_in_gripper}'.")

    def _execute_place_sequence(self, target_coords):
        """Executes the multi-step sequence to place an object."""
        print(f"Brain: Initiating place sequence for '{self.object_in_gripper}' at {target_coords}.")
        x, y, z = target_coords
        angles_above = self._calculate_ik_solution(x, y, self.safe_height)
        self.nervous_system.move_to_angles(angles_above, speed=400)
        time.sleep(2)
        angles_place = self._calculate_ik_solution(x, y, z + 20)
        self.nervous_system.move_to_angles(angles_place, speed=200)
        time.sleep(2)
        self.nervous_system.set_gripper("open")
        time.sleep(1)
        self.nervous_system.move_to_angles(angles_above, speed=200)
        time.sleep(2)
        self.nervous_system.go_home()
        print(f"Brain: Successfully placed '{self.object_in_gripper}'.")
        self.object_in_gripper = None

    def set_drop_point(self, name, coords):
        """Stores the coordinates for a named drop point."""
        self.drop_points[name.upper()] = coords
        print(f"Brain: Drop point '{name.upper()}' has been defined at {coords}.")
        self.defining_point_name = None # Exit the defining state

    def receive_command(self, command, detections):
        """The main entry point for the Brain to process a command."""
        print(f"\nBrain (Cerebrum): Received command '{command}'")
        parsed_command = self._interpret_with_gemini(command, detections)
        intent = parsed_command.get("intent")
        target = parsed_command.get("target")

        if intent == "pickup":
            if self.object_in_gripper:
                # CORRECTED: Removed the space in 'self.object_in_gripper'
                print(f"Brain: Cannot pickup '{target}', already holding '{self.object_in_gripper}'.")
                return
            target_coords = self._find_target_coords(target, detections)
            if target_coords:
                self._execute_pickup_sequence(target, target_coords)
            else:
                print(f"Brain: I heard you say '{target}', but I don't see it.")

        elif intent == "place":
            if not self.object_in_gripper:
                print("Brain: Cannot place anything, gripper is empty.")
                return
            
            drop_point_coords = self.drop_points.get(target.upper())
            if drop_point_coords:
                self._execute_place_sequence(drop_point_coords)
            else:
                print(f"Brain: I don't know where point '{target}' is. Please define it first.")

        elif intent == "define_point":
            print(f"Brain: OK. Please click on the video feed to define location for point '{target.upper()}'.")
            self.defining_point_name = target.upper()

        else:
            print(f"Brain: I'm not sure how to handle the command. Gemini interpretation was: {parsed_command}")

