import cv2
import cv2.aruco  # Modern import
import time
from ultralytics import YOLO
import threading
from queue import Queue
import numpy as np
import os

class VisionSystem:
    """
    An upgraded, integrated vision system for the robotic arm.
    
    - Runs YOLOv8n and YOLOv10n simultaneously.
    - Implements "Winner Takes All" logic to select the best detection.
    - Uses a 60% confidence threshold.
    - Includes the ArUco "Smart Detector" for calibration.
    """
    
    # --- *** UPDATED: 60% threshold *** ---
    def __init__(self, video_source=None, conf_threshold=0.60):
        """
        Initializes the vision system, loading all models and calibration data.
        """
        if not video_source:
            self.video_source = 'http://10.35.179.242:8080/video'
        else:
            self.video_source = video_source

        # The consistent resolution we will use for both calibration and detection
        self.frame_width = 480
        self.frame_height = 360

        # --- *** UPDATED: Load both YOLOv8n and YOLOv10n *** ---
        print("Loading YOLOv10n model...")
        self.model_v10 = YOLO('yolov10n.pt')
        print("Loading YOLOv8n model...")
        try:
            self.model_v8 = YOLO('yolov8n.pt')
            print("All models loaded successfully.")
            # Use v8 names as the primary. Assumes classes are the same.
            self.class_names = self.model_v8.names 
        except Exception as e:
            print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            print(f"ERROR: Could not load 'yolov8n.pt'. {e}")
            print("Please make sure 'yolov8n.pt' is downloaded and in the same folder.")
            print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            # Fallback to v10 if v8 fails
            self.model_v8 = None
            self.class_names = self.model_v10.names
        # --- *** END OF UPDATE *** ---

        self.conf_threshold = conf_threshold
        
        # --- Threading & Queues (Original Structure) ---
        self.frame_queue = Queue(maxsize=1) # For raw frames from camera
        self.is_running = False
        self.grabber_thread = None
        
        # --- ArUco "Smart Detector" ---
        print("Initializing ArUco 'Smart Detector' (will check multiple dictionaries)...")
        self.aruco_detectors = []
        aruco_params = cv2.aruco.DetectorParameters()
        common_dicts = [
            ("4x4_50", cv2.aruco.DICT_4X4_50),
            ("6x6_250", cv2.aruco.DICT_6X6_250),
            ("5x5_100", cv2.aruco.DICT_5X5_100),
            ("ARUCO_ORIGINAL", cv2.aruco.DICT_ARUCO_ORIGINAL)
        ]
        for name, dictionary in common_dicts:
            dict_obj = cv2.aruco.getPredefinedDictionary(dictionary)
            self.aruco_detectors.append((name, cv2.aruco.ArucoDetector(dict_obj, aruco_params)))
        
        # --- Load Calibration ---
        self.transformation_matrix = self._load_calibration()

    def _load_calibration(self):
        """
        Loads the calibration matrix file. If not found, prompts the user to run calibration.
        """
        calibration_file = os.path.join(os.path.dirname(__file__), 'calibration_matrix.npy')
        try:
            matrix = np.load(calibration_file)
            print(f"Successfully loaded calibration matrix from: {calibration_file}")
            return matrix
        except FileNotFoundError:
            print("\n-------------------------------------------")
            print(f"ERROR: Calibration file not found at {calibration_file}")
            print("Please run your 'Calibrator.py' script first to generate it.")
            print("-------------------------------------------\n")
            return None

    # --- *** NEW: Helper function for "Winner Takes All" *** ---
    def _calculate_iou(self, box1, box2):
        """Calculates Intersection over Union (IoU) for two bounding boxes [x1, y1, x2, y2]."""
        xI1 = max(box1[0], box2[0])
        yI1 = max(box1[1], box2[1])
        xI2 = min(box1[2], box2[2])
        yI2 = min(box1[3], box2[3])
        
        inter_area = max(0, xI2 - xI1) * max(0, yI2 - yI1)
        if inter_area == 0:
            return 0
            
        box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
        box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])
        
        union_area = box1_area + box2_area - inter_area
        if union_area == 0:
            return 0
            
        return inter_area / union_area

    # --- *** NEW: "Winner Takes All" Non-Maximum Suppression *** ---
    def _winner_takes_all_nms(self, results_v8, results_v10, iou_threshold=0.5):
        """
        Applies NMS across both models.
        The highest confidence detection "wins" and suppresses overlapping ones.
        """
        all_detections = []
        
        # Add YOLOv8 detections
        if self.model_v8 and results_v8[0] is not None:
            for box in results_v8[0].boxes:
                all_detections.append({
                    "bbox": box.xyxy[0].cpu().numpy(),
                    "conf": box.conf[0].cpu().numpy(),
                    "cls": box.cls[0].cpu().numpy(),
                    "model": "v8"
                })

        # Add YOLOv10 detections
        if results_v10[0] is not None:
            for box in results_v10[0].boxes:
                all_detections.append({
                    "bbox": box.xyxy[0].cpu().numpy(),
                    "conf": box.conf[0].cpu().numpy(),
                    "cls": box.cls[0].cpu().numpy(),
                    "model": "v10"
                })
            
        # Sort all detections by confidence, descending
        all_detections.sort(key=lambda x: x['conf'], reverse=True)
        
        final_detections = []
        while all_detections:
            # Pop the highest-confidence detection
            winner = all_detections.pop(0)
            final_detections.append(winner)
            
            # Create a new list of detections to keep
            remaining_detections = []
            for det in all_detections:
                # Compare winner to this detection
                if det['cls'] != winner['cls'] or self._calculate_iou(winner['bbox'], det['bbox']) < iou_threshold:
                    # Keep it if it's a different class or doesn't overlap much
                    remaining_detections.append(det)
            
            # Overwrite the list with the ones we're keeping
            all_detections = remaining_detections
            
        return final_detections

    def run_calibration(self, width_mm=400, height_mm=300):
        """
        An integrated, user-guided process to calibrate the camera using ArUco markers.
        (This method is unchanged from the previous "Smart Detector" version)
        """
        cap = cv2.VideoCapture(self.video_source)
        if not cap.isOpened():
            print(f"FATAL ERROR: Could not open video source at {self.video_source}.")
            return

        window_name = "Camera Calibration - Detecting ArUco Markers"
        cv2.namedWindow(window_name)

        print("\n--- Automatic Camera Calibration Utility ---")
        print("Instructions:")
        print("1. Place ArUco markers at the corners of your workspace (ID 1: TL, 2: TR, 3: BR, 4: BL).")
        print(f"2. This script assumes the real-world distance between markers is {width_mm}mm wide and {height_mm}mm tall.")
        print("3. Ensure all four markers are visible. The system will detect them and save the calibration file.")
        
        marker_pixel_pts = {} # Use this to store the center points
        temp_matrix = None
        found_dictionary_name = ""
        
        while True:
            ret, frame = cap.read()
            if not ret: continue

            frame_resized = cv2.resize(frame, (self.frame_width, self.frame_height))
            frame_annotated = frame_resized.copy() # Draw on a copy
            
            ids = None
            corners = None
            for dict_name, detector in self.aruco_detectors:
                corners_d, ids_d, _ = detector.detectMarkers(frame_resized)
                if ids_d is not None:
                    ids = ids_d
                    corners = corners_d
                    found_dictionary_name = dict_name # We found a match!
                    break # Stop checking other dictionaries

            if ids is not None:
                cv2.aruco.drawDetectedMarkers(frame_annotated, corners, ids)
                cv2.putText(frame_annotated, f"Detected with: {found_dictionary_name}", 
                            (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                marker_pixel_pts.clear() 
                for i, marker_id in enumerate(ids.flatten()):
                    if marker_id in [1, 2, 3, 4]:
                        marker_corners = corners[i][0]
                        center_x = int(np.mean(marker_corners[:, 0]))
                        center_y = int(np.mean(marker_corners[:, 1]))
                        marker_pixel_pts[marker_id] = (center_x, center_y)
                        cv2.circle(frame_annotated, (center_x, center_y), 5, (0, 0, 255), -1)
                        cv2.putText(frame_annotated, str(marker_id), (center_x, center_y - 10), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            if len(marker_pixel_pts) == 4:
                cv2.putText(frame_annotated, "All 4 markers found! Press 's' to save.", 
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                src_points = np.float32([
                    marker_pixel_pts[1], # Center of marker 1
                    marker_pixel_pts[2], # Center of marker 2
                    marker_pixel_pts[3], # Center of marker 3
                    marker_pixel_pts[4]  # Center of marker 4
                ])
                dst_points = np.float32([[0, 0], [width_mm, 0], [width_mm, height_mm], [0, height_mm]])
                temp_matrix = cv2.getPerspectiveTransform(src_points, dst_points)
            else:
                 cv2.putText(frame_annotated, f"Found {len(marker_pixel_pts)}/4 markers.", 
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            cv2.imshow(window_name, frame_annotated) 
            key = cv2.waitKey(1) & 0xFF

            if key == ord('s'):
                if temp_matrix is not None:
                    self.transformation_matrix = temp_matrix
                    output_file = os.path.join(os.path.dirname(__file__), 'calibration_matrix.npy')
                    np.save(output_file, self.transformation_matrix)
                    print("\n-------------------------------------------")
                    print("SUCCESS! Calibration complete.")
                    print(f"Saved using dictionary: {found_dictionary_name}")
                    print(f"Transformation matrix saved to: {output_file}")
                    print("-------------------------------------------")
                    time.sleep(3) 
                    break
                else:
                    print("Cannot save, all 4 markers not yet found.")
            
            if key == 27 or key == ord('q'): 
                print("Calibration cancelled by user.")
                break

        cap.release()
        cv2.destroyAllWindows()
        print("Calibration tool closed.")

    def convert_pixel_to_world(self, px, py):
        """Converts pixel coordinates (from the resized frame) to real-world millimeters."""
        if self.transformation_matrix is None: return None
        pixel_coords = np.array([[[float(px), float(py)]]], dtype=np.float32)
        world_coords_3d = cv2.perspectiveTransform(pixel_coords, self.transformation_matrix)
        if world_coords_3d is None or len(world_coords_3d) == 0:
            return None
        return world_coords_3d[0][0]

    # This is the original "laggy" frame grabber. It just queues frames.
    def _frame_grabber_thread(self):
        """Internal method to continuously grab frames from the camera."""
        cap = cv2.VideoCapture(self.video_source)
        if not cap.isOpened():
            self.is_running = False; return

        while self.is_running:
            ret, frame = cap.read()
            if not ret:
                cap.release(); time.sleep(2); cap = cv2.VideoCapture(self.video_source)
                continue
            if not self.frame_queue.empty():
                try: self.frame_queue.get_nowait()
                except Queue.empty: pass
            self.frame_queue.put(frame)
        cap.release()

    def start(self):
        """Starts the vision system thread."""
        if self.is_running: return True
        self.transformation_matrix = self._load_calibration() 
        if self.transformation_matrix is None:
            print("Vision system cannot start: calibration matrix is missing.")
            return False
            
        self.is_running = True
        self.grabber_thread = threading.Thread(target=self._frame_grabber_thread, daemon=True)
        self.grabber_thread.start()
        print("Vision System is online.")
        return True

    def stop(self):
        """Stops the vision system thread."""
        self.is_running = False
        if self.grabber_thread: self.grabber_thread.join()
        print("Vision System has been shut down.")

    # --- *** UPDATED: This function now runs BOTH models *** ---
    def get_latest_frame_and_detections(self):
        """
        Gets the latest frame, runs detection, and converts coordinates for each detection.
        This is the "laggy" version that runs detection in the main loop.
        """
        if not self.is_running or self.frame_queue.empty(): 
            return None, None, []
        
        frame = self.frame_queue.get()
        if frame is None:
            return None, None, []
            
        frame_resized = cv2.resize(frame, (self.frame_width, self.frame_height))
        if frame_resized is None:
            return None, None, []
            
        # --- Run BOTH models (This will be slow) ---
        results_v10 = self.model_v10(frame_resized, conf=self.conf_threshold, verbose=False)
        results_v8 = [None] # Default
        if self.model_v8:
            results_v8 = self.model_v8(frame_resized, conf=self.conf_threshold, verbose=False)

        # --- Apply "Winner Takes All" ---
        final_detections = self._winner_takes_all_nms(results_v8, results_v10)
        
        # --- Process and draw the final "winner" detections ---
        annotated_frame = frame_resized.copy()
        detections_for_brain = []

        for det in final_detections:
            x1, y1, x2, y2 = map(int, det['bbox'])
            
            # --- *** BUG FIX HERE *** ---
            conf = det['conf'] # Was 'confidence', now corrected to 'conf'
            # --- *** END OF BUG FIX *** ---
            
            cls_id = int(det['cls'])
            model_name = det['model']
            name = self.class_names[cls_id]

            center_x = (x1 + x2) // 2
            center_y = (y1 + y2) // 2
            world_coords = self.convert_pixel_to_world(center_x, center_y)
            
            detection_data = {
                "name": name,
                "confidence": float(conf),
                "pixel_coords_bbox": (x1, y1, x2, y2),
                "pixel_coords_center": (center_x, center_y),
                "model": model_name # Track which model won
            }
            if world_coords is not None:
                detection_data["world_x"] = world_coords[0]
                detection_data["world_y"] = world_coords[1]
                detection_data["world_z"] = 0
            detections_for_brain.append(detection_data)

            # --- Manual Plotting ---
            color = (0, 255, 0) if model_name == 'v8' else (255, 0, 0) # v8=Green, v10=Blue
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
            
            label = f"{name} ({model_name}): {conf:.2f}"
            (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(annotated_frame, (x1, y1 - h - 5), (x1 + w, y1), color, -1)
            cv2.putText(annotated_frame, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
            
            if world_coords is not None:
                cv2.circle(annotated_frame, (center_x, center_y), 5, (0, 0, 255), -1)
                text = f"({world_coords[0]:.0f}, {world_coords[1]:.0f})mm"
                cv2.putText(annotated_frame, text, (center_x - 30, center_y + 30), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        
        return frame_resized, annotated_frame, detections_for_brain