import serial
import time

# --- Configuration ---
ARDUINO_PORT = "COM3"
BAUD_RATE = 115200
SWEEP_SPEED_DELAY = 0.02 # Seconds between each 1-degree step. Higher is slower.

# Define the safe zones and array index for each component
# Format: { "Name": [MIN_ANGLE, MAX_ANGLE, ARRAY_INDEX] }
SERVO_CONFIG = {
    "Base":      [0, 180, 0],
    "Shoulder":  [0, 170, 1],
    "Elbow":     [56, 108, 2],
    "Wrist":     [15, 180, 3],
    "WristRoll": [0, 166, 4],
    "Gripper":   [0, 85, 5]
}

def get_previous_teta():
    """Reads the last saved set of angles from the text file."""
    try:
        with open("prev_teta.txt", "r") as text_file:
            prev_teta_string = text_file.read()
        prev_teta = [int(float(i)) for i in prev_teta_string.strip().split(";") if i]
        return prev_teta
    except FileNotFoundError:
        print("Warning: prev_teta.txt not found. Using default home angles.")
        return [0, 60, 56, 150, 90, 0]

def write_arduino(arm_serial, angles, active_component_name, active_angle):
    """Formats the full angle list and sends it to the Arduino."""
    angles_to_send = angles.copy()
    angles_to_send[0] = 180 - angles_to_send[0] # Invert Base
    angles_to_send[3] = 180 - angles_to_send[3] # Invert Wrist
    
    angle_string = ','.join([str(int(elem)) for elem in angles_to_send])
    final_command = f"P{angle_string},200\n"
    
    arm_serial.write(final_command.encode('utf-8'))
    print(f"Testing {active_component_name}: {active_angle}°   ", end='\r')

def main():
    """Main function to run an automated sweep test on a selected component."""
    # --- Component Selection ---
    print("Select a component to test:")
    component_list = list(SERVO_CONFIG.keys())
    for i, name in enumerate(component_list):
        print(f"  {i+1}: {name}")
    
    try:
        choice = int(input("Enter your choice (1-6): ")) - 1
        if not 0 <= choice < len(component_list):
            raise ValueError
        component_to_test = component_list[choice]
    except (ValueError, IndexError):
        print("Invalid choice. Exiting.")
        return

    # --- Setup ---
    config = SERVO_CONFIG[component_to_test]
    min_angle, max_angle, angle_index = config

    arduino = None
    try:
        arduino = serial.Serial(ARDUINO_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)
        print(f"Successfully connected to Arduino on {ARDUINO_PORT}")
    except serial.SerialException as e:
        print(f"Error connecting to Arduino: {e}")
        return

    current_arm_angles = get_previous_teta()
    print(f"Arm starting at angles: {current_arm_angles}")
    print(f"Starting automated sweep for {component_to_test}. Press Ctrl+C to stop.")
    time.sleep(1)

    # --- Main Test Loop ---
    try:
        while True:
            print(f"\nSweeping {component_to_test} to MAX angle...")
            for angle in range(min_angle, max_angle + 1):
                current_arm_angles[angle_index] = angle
                write_arduino(arduino, current_arm_angles, component_to_test, angle)
                time.sleep(SWEEP_SPEED_DELAY)
            
            time.sleep(1)

            print(f"\nSweeping {component_to_test} to MIN angle...")
            for angle in range(max_angle, min_angle - 1, -1):
                current_arm_angles[angle_index] = angle
                write_arduino(arduino, current_arm_angles, component_to_test, angle)
                time.sleep(SWEEP_SPEED_DELAY)
            
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\nProgram stopped by user.")
    finally:
        if arduino and arduino.is_open:
            arduino.close()
            print("Serial port closed.")

if __name__ == "__main__":
    main()
