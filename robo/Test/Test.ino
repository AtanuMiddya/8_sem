/*
  Component Test Sketch (Corrected)
  - A versatile sketch for testing individual arm components.
  - Fixes the I2C address initialization for the PCA9G85 board.
*/

#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// CORRECTED: Explicitly provide the I2C address (0x40) for the PCA9685
Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver(0x40);

// Define Channels from your notes
// EDITED: Swapped Wrist and Gripper channels to match the latest observation.
#define BASE_SERVO_CHANNEL        0
#define SHOULDER_SERVO_CHANNEL    1
#define ELBOW_SERVO_CHANNEL       5
#define WRIST_PITCH_SERVO_CHANNEL 2  // Was 3, changed to 2 as this is what moves with 'G'
#define WRIST_ROLL_SERVO_CHANNEL  4
#define GRIPPER_SERVO_CHANNEL     3  // Was 2, changed to 3

// Servo Pulse Config
#define SERVOMIN  150
#define SERVOMAX  600
#define SERVO_FREQ 50

void setup() {
  Serial.begin(115200);
  Serial.println("Test Sketch Ready (All Components).");
  
  pwm.begin();
  pwm.setPWMFreq(SERVO_FREQ);
  
  // Give everything a moment to initialize
  delay(10); 
}

void loop() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    
    // Use a single character for the command to make parsing simpler
    char command_char = command.charAt(0);
    int angle = command.substring(1).toInt();

    switch (command_char) {
      case 'G':
        angle = constrain(angle, 0, 80);   // Gripper safe zone
        setServoAngle(GRIPPER_SERVO_CHANNEL, angle);
        break;
      case 'W':
        angle = constrain(angle, 0, 175);  // Wrist Pitch safe zone
        setServoAngle(WRIST_PITCH_SERVO_CHANNEL, angle);
        break;
      case 'R':
        angle = constrain(angle, 0, 160);  // Wrist Roll safe zone
        setServoAngle(WRIST_ROLL_SERVO_CHANNEL, angle);
        break;
      case 'E':
        angle = constrain(angle, 60, 100); // Elbow safe zone
        setServoAngle(ELBOW_SERVO_CHANNEL, angle);
        break;
      case 'S':
        angle = constrain(angle, 0, 165);  // Shoulder safe zone
        setServoAngle(SHOULDER_SERVO_CHANNEL, angle);
        break;
      case 'B':
        angle = constrain(angle, 0, 180);  // Base safe zone
        setServoAngle(BASE_SERVO_CHANNEL, angle);
        break;
    }
  }
}

void setServoAngle(uint8_t channel, int angle) {
  int pulselength = map(angle, 0, 180, SERVOMIN, SERVOMAX);
  pwm.setPWM(channel, 0, pulselength);
}
