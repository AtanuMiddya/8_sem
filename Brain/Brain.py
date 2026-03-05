import time
import requests
import json
from math import sqrt
# This relative import works correctly when called from Master.py
from . import solverNNA as ik_solver
from .nervousSystem import NervousSystem

class Brain:
    """
    The "Cerebrum" of the robot. This is the high-level planner.
    It understands abstract goals, plans multi-step action sequences,
    uses the IK solver to calculate movements, and sends simple commands
    to the NervousSystem.
    """
    def __init__(self, nervous_system: NervousSystem):
        """
        Initializes the Brain.
        :param nervous_system: An instance of the NervousSystem class.
        """
        self.nervous_system = nervous_system
        
        # --- CRITICAL SECURITY WARNING ---
        # Your previous code exposed a live API key.
        # I have removed it. Never paste API keys into public forums.
        # Please go to your Google Cloud console and DELETE that key immediately.
        # Then, create a new key and store it securely (e.g., in an environment variable).
        self.api_key = "AIzaSyAtLuc9ZQBsl6S4A5aUnd1l3_r8Kranqko" # <-- PUT YOUR NEW KEY HERE
        if self.api_key == "AIzaSyAtLuc9ZQBsl6S4A5aUnd1l3_r8Kranqko":
             print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
             print("CRITICAL: API KEY MISSING in Brain/Brain.py")
             print("Please replace 'YOUR_GEMINI_API_KEY_HERE' with a valid key.")
             print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

        # --- Memory and State ---
        self.object_in_gripper = None # Remembers what it's holding
        self.defining_point_name = None # State for when we are defining a point (e.g., 'A', 'B')
        self.drop_points = {} # Stores the coordinates of defined points, like {'A': (x, y, z)}
        
        # --- Predefined Positions and Heights (in mm) ---
        self.safe_height = 150 # A safe Z-height for moving above objects
        self.pickup_approach_height = 50 # Height to approach an object before grabbing

    def _interpret_with_gemini(self, command, detections):
        """
        Decomposes a complex command into a sequence of simple actions using the Gemini API.
        """
        detected_object_names = list(set([d['name'] for d in detections]))
        
        # --- *** UPDATED SYSTEM PROMPT *** ---
        # We have added new intents: "open_gripper", "close_gripper", and "go_home".
        system_instruction = f"""
        You are an expert roboticist who functions as a task planner. Your job is to take a user's natural language command and decompose it into a JSON list of simple, sequential actions.

        The available objects are: {detected_object_names}.
        There are several possible intents: "pickup", "place", "define_point", "open_gripper", "close_gripper", "go_home".

        Your response MUST be a JSON list of objects, where each object has an "intent" and an optional "target".

        - "pickup": The target MUST be one of the available objects.
        - "place": The target can be a named point (e.g., "A", "B") or another object from the available list (e.g., "cup").
        - "define_point": The target is the name for the new point (e.g., "A", "B").
        - "open_gripper": Does not need a target.
        - "close_gripper": Does not need a target.
        - "go_home": Does not need a target.

        Analyze the user's command and break it down into the correct sequence.
        
        Example (Compound Command):
        Command: "pickup the bottle and place it at point a"
        Response: [
            {{"intent": "pickup", "target": "bottle"}},
            {{"intent": "place", "target": "A"}}
        ]
        
        Example (Simple Command):
        Command: "open the gripper"
        Response: [
            {{"intent": "open_gripper"}}
        ]
        
        Example (Simple Command):
        Command: "go home"
        Response: [
            {{"intent": "go_home"}}
        ]

        If the command is unintelligible, return an empty list: [].
        """
        # --- *** END OF UPDATED PROMPT *** ---
        
        # Using gemini-2.5-flash-preview-09-2025 as it is newer
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={self.api_key}"
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
            return []

    def _calculate_ik_solution(self, x, y, z):
        """
        Calculates the full 6-servo angle solution for a target coordinate.
        This function now fully trusts the solver to handle all safety checks.
        """
        base_angles = ik_solver.move_to_position_cart(x, y, z)
        current_state = self.nervous_system._get_current_state()
        wrist_roll = current_state[4]
        gripper = current_state[5]
        return base_angles + [wrist_roll, gripper]

    def _find_target_coords(self, target_name, detections):
        """Finds the real-world XYZ coordinates of a detected object or a defined point."""
        if target_name.upper() in self.drop_points:
            return self.drop_points[target_name.upper()]
        for detection in detections:
            if detection['name'] == target_name:
                # Use a default Z height for picked-up objects (e.g., 10mm off the ground)
                z_coord = detection.get('world_z', 10.0) 
                return (detection['world_x'], detection['world_y'], z_coord)
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
        
        # --- This is the pickup height (z) ---
        angles_pickup = self._calculate_ik_solution(x, y, z)
        self.nervous_system.move_to_angles(angles_pickup, speed=100)
        time.sleep(2)
        
        self.nervous_system.set_gripper("closed")
        time.sleep(1)
        
        # Lift up to approach height
        self.nervous_system.move_to_angles(angles_approach, speed=100)
        time.sleep(1)
        
        # Go to safe height
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

        angles_place = self._calculate_ik_solution(x, y, z + 20) # Place 20mm above the target Z
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
        self.defining_point_name = None

    def receive_command(self, command, detections):
        """The main entry point for the Brain to process a command sequence."""
        print(f"\nBrain (Cerebrum): Received command '{command}'")

        # --- *** NEW: Direct Command "Pre-Filter" *** ---
        # This handles simple commands instantly without calling the API.
        norm_cmd = command.lower().strip()
        
        if norm_cmd == "open the gripper" or norm_cmd == "open your hand":
            print("Brain: Executing direct command: open_gripper")
            self.nervous_system.set_gripper("open")
            return # We are done

        elif norm_cmd == "close the gripper" or norm_cmd == "close your hand":
            print("Brain: Executing direct command: close_gripper")
            self.nervous_system.set_gripper("closed")
            return # We are done

        elif norm_cmd == "go home" or norm_cmd == "reset" or norm_cmd == "go to sleep":
            print("Brain: Executing direct command: go_home")
            self.nervous_system.go_home()
            return # We are done
        
        # --- *** END OF NEW BLOCK *** ---

        # If it wasn't a simple command, proceed to Gemini for complex planning
        print("Brain: Command is complex. Sending to Gemini for planning...")
        command_sequence = self._interpret_with_gemini(command, detections)

        if not command_sequence:
            print(f"Brain: I'm not sure how to handle the command. Gemini could not interpret it.")
            return

        print(f"Brain: Understood command sequence: {command_sequence}")

        for action in command_sequence:
            intent = action.get("intent")
            target = action.get("target") # This is OK if it's None

            if intent == "pickup":
                if self.object_in_gripper == target:
                    print(f"Brain: I am already holding the '{target}'. Skipping pickup step.")
                    continue 
                elif self.object_in_gripper is not None:
                    print(f"Brain: Cannot pickup '{target}', I am already holding '{self.object_in_gripper}'. Aborting sequence.")
                    break

                target_coords = self._find_target_coords(target, detections)
                if target_coords:
                    self._execute_pickup_sequence(target, target_coords)
                else:
                    print(f"Brain: I can't find '{target}' in the camera view. Aborting sequence.")
                    break

            elif intent == "place":
                if not self.object_in_gripper:
                    print("Brain: Cannot 'place', gripper is empty. Aborting sequence.")
                    break
                target_coords = self._find_target_coords(target, detections)
                if target_coords:
                    self._execute_place_sequence(target_coords)
                else:
                    print(f"Brain: I can't find the destination '{target}'. Aborting sequence.")
                    break

            elif intent == "define_point":
                print(f"Brain: OK. Please click on the video feed to define location for point '{target.upper()}'.")
                self.defining_point_name = target.upper()

            # --- *** NEW: Handle simple intents planned by Gemini *** ---
            elif intent == "open_gripper":
                print("Brain: Executing planned command: open_gripper")
                self.nervous_system.set_gripper("open")
                time.sleep(1) # Give it time to execute

            elif intent == "close_gripper":
                print("Brain: Executing planned command: close_gripper")
                self.nervous_system.set_gripper("closed")
                time.sleep(1) # Give it time to execute

            elif intent == "go_home":
                print("Brain: ExecTuting planned command: go_home")
                self.nervous_system.go_home()
                time.sleep(2) # Give it time to execute
            # --- *** END OF NEW BLOCK *** ---

            else:
                print(f"Brain: I don't understand the intent '{intent}'. Aborting sequence.")
                break