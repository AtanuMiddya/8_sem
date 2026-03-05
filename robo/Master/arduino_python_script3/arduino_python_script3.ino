#include <WiFi.h>
#include <WebServer.h>

// ---------- WiFi ----------
const char* ssid = "ESP32-Servo";
const char* password = "12345678";

// ---------- Servo ----------
#define SERVO_PIN 18
#define PWM_CHANNEL 0
#define PWM_FREQ 50
#define PWM_RESOLUTION 16

WebServer server(80);

int currentAngle = 90;
int targetAngle = 90;
int speedDelay = 5;

// ---------- Angle → Duty ----------
uint32_t angleToDuty(int angle) {
  // 50Hz period = 20ms
  // duty range for servo ≈ 0.5ms–2.5ms
  uint32_t minDuty = 1638;  // 0.5ms
  uint32_t maxDuty = 8192;  // 2.5ms
  return map(angle, 0, 180, minDuty, maxDuty);
}

// ---------- Smooth Move ----------
void moveServoSmooth() {
  if (currentAngle == targetAngle) return;

  int step = (currentAngle < targetAngle) ? 1 : -1;

  while (currentAngle != targetAngle) {
    currentAngle += step;
    ledcWrite(PWM_CHANNEL, angleToDuty(currentAngle));
    delay(speedDelay);
  }
}

// ---------- Web Page ----------
String webpage() {
  return R"rawliteral(
<!DOCTYPE html>
<html>
<head>
<title>ESP32 Servo Tester</title>
<style>
body { background:#111; color:#0f0; font-family:Arial; text-align:center; }
input[type=range] { width:80%; }
.box { border:1px solid #0f0; padding:20px; margin:20px; }
</style>
</head>
<body>

<h2>ESP32 Servo Tester (Direct PWM)</h2>

<div class="box">
<h3>Servo Angle</h3>
<input type="range" min="0" max="180" value="90"
oninput="setAngle(this.value)">
<p>Angle: <span id="a">90</span>°</p>
</div>

<div class="box">
<h3>Rotation Speed</h3>
<input type="range" min="1" max="20" value="5"
oninput="setSpeed(this.value)">
<p>Delay: <span id="s">5</span> ms</p>
</div>

<script>
function setAngle(v){
 document.getElementById('a').innerHTML=v;
 fetch('/angle?val='+v);
}
function setSpeed(v){
 document.getElementById('s').innerHTML=v;
 fetch('/speed?val='+v);
}
</script>

</body>
</html>
)rawliteral";
}

// ---------- Handlers ----------
void handleRoot() {
  server.send(200, "text/html", webpage());
}

void handleAngle() {
  if (server.hasArg("val"))
    targetAngle = server.arg("val").toInt();
  server.send(200, "text/plain", "OK");
}

void handleSpeed() {
  if (server.hasArg("val"))
    speedDelay = server.arg("val").toInt();
  server.send(200, "text/plain", "OK");
}

// ---------- Setup ----------
void setup() {
  Serial.begin(115200);

  ledcSetup(PWM_CHANNEL, PWM_FREQ, PWM_RESOLUTION);
  ledcAttachPin(SERVO_PIN, PWM_CHANNEL);
  ledcWrite(PWM_CHANNEL, angleToDuty(90));

  WiFi.softAP(ssid, password);
  Serial.println(WiFi.softAPIP());

  server.on("/", handleRoot);
  server.on("/angle", handleAngle);
  server.on("/speed", handleSpeed);
  server.begin();
}

// ---------- Loop ----------
void loop() {
  server.handleClient();
  moveServoSmooth();
}
