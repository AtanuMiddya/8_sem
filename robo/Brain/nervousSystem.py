import serial
import time
from serial.tools import list_ports
import os

class NervousSystem:
    """
    The low-level controller for the robotic arm. It does not think or plan.
    Its only job is to receive simple, direct commands (e.g., a list of angles)
    and transmit them to the Arduino (the "Body").
    """
    def __init__(self, port="COM3", baud_rate=115200):
        self.port = port
        self.baud_rate = baud_rate
        self.arduino = None
        # Define default/home position angles for all 6 servos
        self.home_angles = [90, 85, 100, 150, 90, 0] # Base, Shoulder, Elbow, Wrist, WristRoll, Gripper (0=closed)

    def connect(self):
        """Connects to the Arduino via the specified serial port."""
        try:
            self.arduino = serial.Serial(self.port, self.baud_rate, timeout=2)
            time.sleep(2)
            print(f"Nervous System connected to Body on {self.port}")
            return True
        except serial.SerialException as e:
            print(f"Error connecting Nervous System to Body: {e}")
            return False

    def disconnect(self):
        """Disconnects from the Arduino."""
        if self.arduino and self.arduino.is_open:
            self.arduino.close()
            print("Nervous System disconnected from Body.")

    def _get_current_state(self):
        """Reads the last known angles from the state file."""
        try:
            with open("prev_teta.txt", "r") as f:
                state_str = f.read()
                return [int(float(i)) for i in state_str.strip().split(";") if i]
        except FileNotFoundError:
            return self.home_angles

    def _save_current_state(self, angles):
        """Saves the current angles to the state file."""
        with open("prev_teta.txt", "w") as f:
            f.write(";".join(map(str, angles)) + ";")
    
    def _write_to_arduino(self, angles, speed=200):
        """Formats and sends the angle command string to the Arduino."""
        if not self.arduino or not self.arduino.is_open:
            print("Error: Not connected to Body.")
            return

        # Create a mutable copy and apply physical inversions
        angles_to_send = list(angles)
        angles_to_send[0] = 180 - angles_to_send[0]  # Invert Base
        angles_to_send[3] = 180 - angles_to_send[3]  # Invert Wrist

        angle_string = ','.join([str(int(elem)) for elem in angles_to_send])
        final_command = f"P{angle_string},{speed}\n"
        
        self.arduino.write(final_command.encode('utf-8'))
        self._save_current_state(angles) # Save the logical (non-inverted) angles

    def move_to_angles(self, angles, speed=200):
        """Public method to command the arm to move to a specific set of angles."""
        print(f"Nervous System: Moving to {angles}")
        self._write_to_arduino(angles, speed)

    def set_gripper(self, state, speed=200):
        """Commands the gripper to open or close without moving other joints."""
        current_angles = self._get_current_state()
        if state == "open":
            current_angles[5] = 85 # Gripper open angle
        else: # "closed"
            current_angles[5] = 0  # Gripper closed angle
        self.move_to_angles(current_angles, speed)

    def go_home(self, speed=200):
        """Commands the arm to move to its predefined home position."""
        self.move_to_angles(self.home_angles, speed)
