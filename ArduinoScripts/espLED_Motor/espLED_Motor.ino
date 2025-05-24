#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ESP8266HTTPClient.h>
#include <DHT.h>
#include <AccelStepper.h>
#include "config.h"

// Pins & Setup
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

// Stepper Control
int currentAngle = 0;
int targetAngle = 0;

// Sensor- & Zeitsteuerung
float temperature = NAN;
float humidity = NAN;

unsigned long lastReadTime = 0;
unsigned long lastRetryTime = 0;
const unsigned long readInterval = 100000;    // 100 s normal
const unsigned long retryInterval = 5000;     // 5 s bei Fehler
bool sensorReady = false;

void setup() {
  Serial.begin(115200);
  Serial.println("\nBooting...");

  pinMode(ledPin, OUTPUT);
  stepper.setMaxSpeed(100);
  stepper.setAcceleration(100);

  dht.begin();

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("");
  Serial.print("Connected to WiFi. IP address: ");
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
  server.handleClient();
  handleStepperMovement();

  unsigned long now = millis();

  // Wenn Sensor nicht bereit → Retry alle 5s
  if (!sensorReady && now - lastRetryTime >= retryInterval) {
    lastRetryTime = now;
    tryReadSensor();
  }

  // Normaler Lesezyklus alle 100s
  if (sensorReady && now - lastReadTime >= readInterval) {
    lastReadTime = now;
    tryReadSensor();
  }
}

// Sensor lesen
void tryReadSensor() {
  float h = dht.readHumidity();
  float t = dht.readTemperature();

  if (!isnan(h) && !isnan(t)) {
    humidity = h;
    temperature = t;
    sensorReady = true;
    Serial.printf("DHT OK: %.1f°C, %.1f%%\n", temperature, humidity);
    sendData();
  } else {
    sensorReady = false;
    Serial.println("DHT read failed.");
  }
  yield();  // wichtig für Watchdog
}

// HTTP POST senden
void sendData() {
  if (WiFi.status() == WL_CONNECTED) {
    WiFiClient client;
    HTTPClient http;
    http.begin(client, serverUrl);
    http.setTimeout(2000);
    http.addHeader("Content-Type", "application/json");

    String payload = "{\"device_id\": \"ESP_01\", \"temperature\": " + String(temperature) + ", \"humidity\": " + String(humidity) + "}";
    int code = http.POST(payload);
    http.end();

    Serial.printf("HTTP POST [%d] → %s\n", code, payload.c_str());
  } else {
    Serial.println("WiFi not connected. Skipping POST.");
  }
}

// Webserver-Funktionen
void handleRoot() {
  server.send(200, "text/plain", "ESP8266 LED Control");
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
  if (server.arg("angle") != "") {
    targetAngle = server.arg("angle").toInt() * 2000 / 360;
    server.send(200, "text/plain", "Angle set to: " + String(targetAngle));
  } else {
    server.send(400, "text/plain", "Missing angle parameter");
  }
}

void getAngle() {
  server.send(200, "text/plain", String(currentAngle));
}

// Stepper Motor Steuerung
void handleStepperMovement() {
  if (stepper.distanceToGo() == 0) {
    stepper.moveTo(targetAngle);
  }
  stepper.run();
  currentAngle = stepper.currentPosition();
}
