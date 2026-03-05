# Eyes/Calibrator.py
"""
This script is used only for calibrating the camera.
It imports the main VisionSystem class from the 'Vision.py' file
in this same folder and calls its built-in calibration method.
"""

from Vision import VisionSystem
import time

# --- CONFIGURATION ---
# IMPORTANT: Measure the real-world distance (in millimeters) 
# between your ArUco markers to form a rectangle.
WORKSPACE_WIDTH_MM = 400
WORKSPACE_HEIGHT_MM = 300

def main():
    """
    Initializes the VisionSystem and starts the calibration process.
    """
    print("Initializing Vision System to begin calibration...")
    
    # Create an instance of the VisionSystem.
    # We don't need to pass the video_source argument,
    # as the __init__ method in Vision.py will use the default URL.
    vision_system = VisionSystem()
    
    # Start the user-guided calibration process
    # This will open a window and guide you to find the 4 markers.
    vision_system.run_calibration(
        width_mm=WORKSPACE_WIDTH_MM, 
        height_mm=WORKSPACE_HEIGHT_MM
    )

    print("\nCalibration script finished.")
    print("The file 'calibration_matrix.npy' should now be in your 'Eyes' folder.")
    print("You can now run your Master.py script.")

if __name__ == "__main__":
    main()