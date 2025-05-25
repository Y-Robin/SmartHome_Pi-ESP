#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ESP8266HTTPClient.h>
#include <DHT.h>
#include <AccelStepper.h>
extern "C" {
  #include "user_interface.h"
}
#include "config.h"

// --- Pins & Setup ---
const int motorPin1 = D5;
const int motorPin2 = D6;
const int motorPin3 = D7;
const int motorPin4 = D8;
AccelStepper stepper(AccelStepper::FULL4WIRE, motorPin1, motorPin3, motorPin2, motorPin4);

const int ledPin = D1;
#define DHTPIN D2
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

ESP8266WebServer server(80);

// --- Sensor & Timing ---
float temperature = NAN;
float humidity = NAN;
bool sensorReady = false;

unsigned long lastReadTime = 0;
unsigned long lastRetryTime = 0;
unsigned long lastMemLog = 0;
const unsigned long readInterval = 100000;     // 100 s bei gültigem Sensor
const unsigned long retryInterval = 5000;      // 5 s bei Sensorfehler
const unsigned long memLogInterval = 60000;    // 1 Min Heap-Log
const unsigned long rebootThreshold = 3000;    // min. 3 KB Heap vor Reboot

// --- Stepper ---
int currentAngle = 0;
int targetAngle = 0;

void setup() {
  Serial.begin(115200);
  Serial.println("\nBooting...");

  pinMode(ledPin, OUTPUT);
  dht.begin();
  stepper.setMaxSpeed(100);
  stepper.setAcceleration(100);

  // WiFi verbinden (Initial)
  WiFi.begin(ssid, password);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(true);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("WiFi connected. IP: ");
  Serial.println(WiFi.localIP());

  // Webserver-Routen
  server.on("/", handleRoot);
  server.on("/on", handleLedOn);
  server.on("/off", handleLedOff);
  server.on("/set_angle", HTTP_GET, setAngle);
  server.on("/get_angle", HTTP_GET, getAngle);
  server.begin();
}

void loop() {
  unsigned long now = millis();

  checkWiFiReconnect();
  server.handleClient();
  handleStepperMovement();

  if (!sensorReady && now - lastRetryTime >= retryInterval) {
    lastRetryTime = now;
    tryReadSensor();
  }

  if (sensorReady && now - lastReadTime >= readInterval) {
    lastReadTime = now;
    tryReadSensor();
  }

  // RAM loggen
  if (now - lastMemLog > memLogInterval) {
    lastMemLog = now;
    unsigned long heap = system_get_free_heap_size();
    Serial.printf("Free heap: %lu bytes\n", heap);
    if (heap < rebootThreshold) {
      Serial.println("Heap critically low. Restarting...");
      delay(500);
      ESP.restart();
    }
  }
}

// --- WLAN-Reconnect ---
void checkWiFiReconnect() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi lost. Attempting reconnect...");
    WiFi.disconnect();
    delay(100);
    WiFi.begin(ssid, password);
    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < 5000) {
      delay(100);
      yield();
    }
    if (WiFi.status() == WL_CONNECTED) {
      Serial.println("WiFi reconnected.");
    } else {
      Serial.println("Reconnect failed.");
    }
  }
}

// --- Sensor lesen ---
void tryReadSensor() {
  float h = dht.readHumidity();
  float t = dht.readTemperature();

  if (!isnan(h) && !isnan(t)) {
    humidity = h;
    temperature = t;
    sensorReady = true;
    Serial.printf("Sensor OK: %.1f°C, %.1f%%\n", temperature, humidity);
    sendData();
  } else {
    sensorReady = false;
    Serial.println("DHT read failed.");
  }
  yield();  // Watchdog
}

// --- HTTP senden ---
void sendData() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi not connected. Skipping POST.");
    return;
  }

  WiFiClient client;
  HTTPClient http;
  if (!http.begin(client, serverUrl)) {
    Serial.println("HTTP begin failed.");
    return;
  }

  http.setTimeout(2000);
  http.addHeader("Content-Type", "application/json");

  char payload[128];
  snprintf(payload, sizeof(payload),
           "{\"device_id\":\"ESP_01\",\"temperature\":%.1f,\"humidity\":%.1f}",
           temperature, humidity);

  int code = http.POST(payload);
  http.end();

  Serial.printf("HTTP POST [%d] → %s\n", code, payload);
}

// --- Stepper ---
void handleStepperMovement() {
  if (stepper.distanceToGo() == 0) {
    stepper.moveTo(targetAngle);
  }
  stepper.run();
  currentAngle = stepper.currentPosition();
}

// --- Webserver Handler ---
void handleRoot() {
  server.send(200, "text/plain", "ESP8266 Status OK");
}

void handleLedOn() {
  digitalWrite(ledPin, HIGH);
  server.send(200, "text/plain", "LED is ON");
}

void handleLedOff() {
  digitalWrite(ledPin, LOW);
  server.send(200, "text/plain", "LED is OFF");
}

void setAngle() {
  if (server.hasArg("angle")) {
    targetAngle = server.arg("angle").toInt() * 2000 / 360;
    server.send(200, "text/plain", "Angle set to: " + String(targetAngle));
  } else {
    server.send(400, "text/plain", "Missing angle parameter");
  }
}

void getAngle() {
  server.send(200, "text/plain", String(currentAngle));
}
