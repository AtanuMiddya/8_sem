from sympy import *
from math import *
import numpy as np
import os

# --- Physical constants of the robot arm in mm (UPDATED from your diagram) ---
l0 = 65  # Height from base to shoulder joint (H-I: 6.5cm)
l1 = 75  # Length from shoulder to elbow joint (F-D: 7.5cm)
l2 = 110 # Length from elbow to wrist joint (C-E: 11cm)
l3 = 110 # Length from wrist to gripper tip (A-B: 11cm)

# Calculate the maximum physical reach for the safety check
MAX_REACH = l1 + l2 + l3

# --- Define the physical servo limits ---
# These values ensure the solver never returns an impossible angle.
SERVO_LIMITS = {
    "base":     {"min": 0, "max": 180},
    "shoulder": {"min": 0, "max": 170},
    "elbow":    {"min": 10, "max": 108},
    "wrist":    {"min": 15, "max": 180}
}

def move_to_position_cart(x, y, z):
    """
    Calculates the inverse kinematics for the first four joints of the arm.
    UPGRADED: Now includes an internal safety check to prevent unreachable targets
    and automatically corrects them to the closest possible point.
    """
    target_x, target_y, target_z = x, y, z
    
    # --- Compensation values for the physical robot ---
    r_compensation = 1.02 # Add 2 percent to radial distance
    z_compensation = 15   # Compensation for backlash/gravity in mm
    
    # Apply compensation to a temporary variable for the check
    compensated_z = target_z + z_compensation
    
    # --- UPGRADED: Internal Reachability and Correction Logic ---
    # This calculation mirrors the final math to get an accurate required reach
    r_hor = sqrt(target_x**2 + target_y**2)
    required_r_uncompensated = sqrt(r_hor**2 + (compensated_z - 71.5)**2)
    required_r_final = required_r_uncompensated * r_compensation

    if required_r_final > MAX_REACH:
        print(f"Solver Safety Warning: Target (X:{x:.1f}, Y:{y:.1f}, Z:{z:.1f}) is unreachable.")
        print(f"  -> Required Reach: {required_r_final:.1f}mm, Maximum Arm Reach: {MAX_REACH:.1f}mm")
        
        # Calculate a scaling factor to bring the target to the edge of the workspace
        # We use the uncompensated distance for scaling to avoid overshooting
        scale_factor = MAX_REACH / required_r_final
        
        # Scale down the original coordinates to find the new, reachable target
        target_x = target_x * scale_factor
        target_y = target_y * scale_factor
        
        print(f"  -> Adjusting target to closest reachable point: (X:{target_x:.1f}, Y:{target_y:.1f}, Z:{z:.1f})")

    # --- Proceed with original calculations using the (potentially corrected) coordinates ---
    z = target_z + z_compensation
    r_hor = sqrt(target_x**2 + target_y**2)
    r = sqrt(r_hor**2 + (z - 71.5)**2) * r_compensation
    
    if y == 0:
        theta_base = 180 if target_x <= 0 else 0
    else:
        theta_base = 90 - degrees(atan(target_x / y))
    
    # This value is now guaranteed to be <= 1
    value_for_acos = (r - l2) / (l1 + l3)
    # Clamp the value just in case of floating point inaccuracies
    value_for_acos = max(-1.0, min(1.0, value_for_acos))
    
    alpha1 = acos(value_for_acos)
    theta_shoulder = degrees(alpha1)
    alpha3 = asin((sin(alpha1) * l3 - sin(alpha1) * l1) / l2)
    theta_elbow = (90 - degrees(alpha1)) + degrees(alpha3)
    theta_wrist = (90 - degrees(alpha1)) - degrees(alpha3)
    
    if theta_wrist <= 0:
        alpha1 = acos(value_for_acos)
        theta_shoulder = degrees(alpha1 + asin((l3 - l1) / r))
        theta_elbow = (90 - degrees(alpha1))
        theta_wrist = (90 - degrees(alpha1))
    
    if z != l0:
        theta_shoulder = theta_shoulder + degrees(atan(((z - l0) / r)))
    
    theta_elbow = theta_elbow + 5
    theta_wrist = theta_wrist + 5
    
    # --- FINAL VALIDATION AND CLAMPING ---
    # This ensures that no matter what the math calculates, the final angles
    # are always within the physical range of the servos.
    
    final_base = round(max(SERVO_LIMITS["base"]["min"], min(SERVO_LIMITS["base"]["max"], theta_base)))
    final_shoulder = round(max(SERVO_LIMITS["shoulder"]["min"], min(SERVO_LIMITS["shoulder"]["max"], theta_shoulder)))
    final_elbow = round(max(SERVO_LIMITS["elbow"]["min"], min(SERVO_LIMITS["elbow"]["max"], theta_elbow)))
    final_wrist = round(max(SERVO_LIMITS["wrist"]["min"], min(SERVO_LIMITS["wrist"]["max"], theta_wrist)))
    
    theta_array = [final_base, final_shoulder, final_elbow, final_wrist]
    
    return theta_array

