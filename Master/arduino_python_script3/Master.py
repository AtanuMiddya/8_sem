# master.py

# Standard library imports
import time
import cv2
from queue import Queue
import sys
import os

# --- System Path Configuration ---
# This block dynamically adds your project's root directory to the Python path.
# This allows this script to find and import the other modules from their respective folders.
try:
    # Get the directory of the current script (Master.py)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Navigate up three levels to get to the project root ('FINAL YEAR PROJECT')
    project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
    # Add the project root to the system path
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # Now we can import all the necessary classes
    from Brain.Brain import Brain # The new Cerebrum
    from Brain.nervousSystem import NervousSystem # The new low-level controller
    from Ear.Ear import Ear
    from Eyes.Vision import VisionSystem

except ImportError as e:
    print(f"Error: Could not import a required module. {e}")
    print("Please ensure your folder structure and file capitalization are correct.")
    sys.exit(1)


def main():
    """
    The main function that initializes and runs the fully integrated,
    intelligent robotic arm system.
    """
    print("--- Starting Robotic Arm Control System ---")

    # A thread-safe queue for the Ear to pass commands to the main loop.
    command_queue = Queue()

    # --- 1. Initialize the Nervous System (The "Doer") ---
    # This directly controls the Arduino.
    robot_nervous_system = NervousSystem(port="COM3")
    if not robot_nervous_system.connect():
        print("FATAL: Could not connect to the robot's Nervous System. Exiting.")
        return

    # --- 2. Initialize the Brain (The "Thinker") ---
    # The Brain receives the nervous system instance so it can send commands.
    robot_brain = Brain(nervous_system=robot_nervous_system)

    # --- 3. Initialize the Ear ---
    robot_ear = Ear(command_queue)
    robot_ear.start()

    # --- 4. Initialize the Vision System ---
    robot_vision = VisionSystem()
    if not robot_vision.start():
        print("WARNING: Vision system failed to start. Continuing without camera.")

    # --- Main Control Loop ---
    window_name = "Robotic Arm Control Center"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    prev_frame_time = 0

    try:
        while True:
            # --- Vision Processing ---
            frame, annotated_frame, detections = robot_vision.get_latest_frame_and_detections()

            if annotated_frame is not None:
                # Calculate and display FPS
                new_frame_time = time.time()
                if prev_frame_time > 0:
                    fps = 1 / (new_frame_time - prev_frame_time)
                    cv2.putText(annotated_frame, f"FPS: {int(fps)}", (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)
                prev_frame_time = new_frame_time
                cv2.imshow(window_name, annotated_frame)
            else:
                time.sleep(0.1)

            # --- Voice Command Processing ---
            if not command_queue.empty():
                command = command_queue.get()
                print(f"\n[Master Control] Received command from Ear: '{command}'")

                if command == 'exit':
                    print("[Master Control] Exit command received. Shutting down.")
                    break

                # **CRUCIAL UPDATE:** Send both the text command AND the live
                # vision detections to the Brain for intelligent processing.
                robot_brain.receive_command(command, detections)

            # --- User Input ---
            if cv2.waitKey(1) == 27:
                print("[Master Control] ESC key pressed. Shutting down.")
                break

    finally:
        # --- Graceful Shutdown ---
        print("\n[Master Control] Initiating shutdown...")
        robot_ear.stop()
        robot_vision.stop()
        # Disconnect the nervous system from the Arduino
        robot_nervous_system.disconnect()
        cv2.destroyAllWindows()
        print("[Master Control] System has been shut down successfully.")

if __name__ == "__main__":
    main()
