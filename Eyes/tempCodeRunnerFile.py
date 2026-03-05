import cv2
import numpy as np
from ultralytics import YOLO
import time
import os

# --- CONFIGURATION ---
# Get the absolute path to the directory this script is in
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Save the calibration file in the same directory as this script
CALIBRATION_FILE = os.path.join(SCRIPT_DIR, 'calibration_matrix.npy')

IP_CAM_URL = 'http://10.225.24.109:8080/video' # Using the last known good IP
MODEL_PATH = 'yolov10n.pt'
CONFIDENCE_THRESHOLD = 0.5
# --- END CONFIGURATION ---

class VisionSystem:
    def __init__(self, model_path=MODEL_PATH, camera_url=IP_CAM_URL):
        """
        Initializes the YOLO model, ArUco detector, and camera.
        """
        print(f"Loading {MODEL_PATH} model...")
        self.model = YOLO(model_path)
        print("Model loaded successfully.\n")
        
        # --- THIS IS THE FIX (Part 1) ---
        # This is the modern, correct way to initialize the detector
        self.aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        self.aruco_params = cv2.aruco.DetectorParameters()
        self.aruco_detector = cv2.aruco.ArucoDetector(self.aruco_dict, self.aruco_params)
        # --- END FIX ---

        self.cap = cv2.VideoCapture(camera_url)
        if not self.cap.isOpened():
            print(f"CRITICAL: Failed to open camera at {camera_url}")
            
        self.mtx = None
        self.load_calibration()

    def load_calibration(self):
        """
        Loads the calibration matrix from the file.
        """
        if os.path.exists(CALIBRATION_FILE):
            try:
                with open(CALIBRATION_FILE, 'rb') as f:
                    self.mtx = np.load(f)
                    # Try to load the old dist array, but ignore if it's not there
                    try:
                        np.load(f) 
                    except ValueError:
                        pass
                print(f"Calibration file found and loaded from {CALIBRATION_FILE}")
            except Exception as e:
                print(f"ERROR: Could not load calibration file. It may be corrupt. Error: {e}")
                self.mtx = None
        else:
            print("-" * 43)
            print(f"ERROR: Calibration file not found at {CALIBRATION_FILE}")
            print("Please run your 'Calibrator.py' script first to generate it.")
            print("-" * 43)
            self.mtx = None # Ensure mtx is None if file not found

    def run_calibration(self, width_mm, height_mm):
        """
        Runs a user-guided process to detect ArUco markers and save
        a homography matrix for camera calibration.
        """
        print("\n--- Automatic Camera Calibration Utility ---")
        print("Instructions:")
        print("1. Place ArUco markers at the corners of your workspace (ID 1: TL, 2: TR, 3: BR, 4: BL).")
        print(f"2. This script assumes the real-world distance between markers is {width_mm}mm wide and {height_mm}mm tall.")
        print("3. Ensure all four markers are visible. The system will detect them and save the calibration file.")
        
        # Define the real-world coordinates of the marker centers
        real_world_pts = {
            1: [0, 0],
            2: [width_mm, 0],
            3: [width_mm, height_mm],
            4: [0, height_mm]
        }
        
        while True:
            if not self.cap.isOpened():
                print("Cannot connect to camera. Retrying...")
                self.cap = cv2.VideoCapture(IP_CAM_URL)
                time.sleep(2)
                continue
                
            ret, frame = self.cap.read()
            if not ret:
                print("Failed to grab frame.")
                continue
            
            # Resize for consistency, but you can change this
            frame_resized = cv2.resize(frame, (1024, 768))
            
            # --- THIS IS THE FIX (Part 2) ---
            # Call the .detectMarkers() method on the *detector object*
            # The old static function `cv2.aruco.detectMarkers` no longer exists.
            corners, ids, _ = self.aruco_detector.detectMarkers(frame_resized)
            # --- END FIX ---

            image_pts = {}
            if ids is not None:
                cv2.aruco.drawDetectedMarkers(frame_resized, corners, ids)
                for i, marker_id in enumerate(ids.flatten()):
                    if marker_id in real_world_pts:
                        # Get the center of the marker
                        c = corners[i][0]
                        image_pts[marker_id] = [c[:, 0].mean(), c[:, 1].mean()]

            cv2.imshow("Calibration - Press 's' to save, 'q' to quit", frame_resized)
            key = cv2.waitKey(1) & 0xFF

            if len(image_pts) == 4:
                print(f"All 4 markers found! Press 's' to save calibration.", end='\r')
                if key == ord('s'):
                    # Create the source and destination points for homography
                    src_pts = np.array([image_pts[1], image_pts[2], image_pts[3], image_pts[4]], dtype='float32')
                    dst_pts = np.array([real_world_pts[1], real_world_pts[2], real_world_pts[3], real_world_pts[4]], dtype='float32')
                    
                    # Find the perspective transformation matrix (homography)
                    h, _ = cv2.findHomography(src_pts, dst_pts)
                    
                    with open(CALIBRATION_FILE, 'wb') as f:
                        np.save(f, h)
                        # Save a dummy array to maintain file structure compatibility if needed
                        np.save(f, np.array([])) 
                        
                    print(f"\n--- SUCCESS! ---")
                    print(f"Calibration matrix saved to {CALIBRATION_FILE}")
                    break
            else:
                print(f"Found {len(image_pts)}/4 markers. Looking for all four...", end='\r')
            
            if key == ord('q'):
                print("\nCalibration cancelled by user.")
                break

        self.cap.release()
        cv2.destroyAllWindows()

    # --- Other methods for your main project would go here ---
    # (e.g., process_frame, get_clean_frame)
    
    def __del__(self):
        """
        A destructor to make sure the camera is released when the object is deleted.
        """
        if self.cap:
            self.cap.release()