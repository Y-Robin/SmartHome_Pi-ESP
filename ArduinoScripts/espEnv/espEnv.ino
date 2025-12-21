#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ESP8266HTTPClient.h>
#include <Wire.h>
#include <Adafruit_SHT31.h>

extern "C" {
  #include "user_interface.h"
}

#include "config.h"

// ---------------- Pins ----------------
const int ledPin = D4;   // Onboard LED (GPIO2, active LOW)

// ---------------- Webserver ----------------
ESP8266WebServer server(80);

// ---------------- Sensor ----------------
Adafruit_SHT31 sht30 = Adafruit_SHT31();

// ---------------- Messwerte ----------------
float temperature = NAN;
float humidity    = NAN;
bool sensorReady  = false;

// ---------------- Timing ----------------
unsigned long lastReadTime   = 0;
unsigned long lastRetryTime  = 0;
unsigned long lastMemLog     = 0;

const unsigned long readInterval   = 100000; // 100s
const unsigned long retryInterval  = 5000;   // 5s
const unsigned long memLogInterval = 60000;  // 1 min
const unsigned long rebootThreshold = 3000;  // Heap bytes

// ------------------------------------------------------------

void setup() {
  Serial.begin(115200);
  Serial.println("\nBooting...");

  pinMode(ledPin, OUTPUT);
  digitalWrite(ledPin, HIGH); // LED AUS

  // --- I2C ---
  Wire.begin(D2, D1); // SDA, SCL

  // --- SHT30 ---
  if (!sht30.begin(0x44)) {
    Serial.println("SHT30 not found!");
    sensorReady = false;
  } else {
    Serial.println("SHT30 detected.");
    sensorReady = true;
  }

  // --- WLAN ---
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

  // --- Webserver ---
  server.on("/", handleRoot);
  server.on("/on", handleLedOn);
  server.on("/off", handleLedOff);
  server.begin();
}

// ------------------------------------------------------------

void loop() {
  unsigned long now = millis();

  checkWiFiReconnect();
  server.handleClient();

  if (!sensorReady && now - lastRetryTime >= retryInterval) {
    lastRetryTime = now;
    tryReadSensor();
  }

  if (sensorReady && now - lastReadTime >= readInterval) {
    lastReadTime = now;
    tryReadSensor();
  }

  // Heap überwachen
  if (now - lastMemLog >= memLogInterval) {
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

// ------------------------------------------------------------
// WLAN Reconnect
// ------------------------------------------------------------
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
    }
  }
}

// ------------------------------------------------------------
// Sensor lesen
// ------------------------------------------------------------
void tryReadSensor() {
  float t = sht30.readTemperature();
  float h = sht30.readHumidity();

  if (!isnan(t) && !isnan(h)) {
    temperature = t;
    humidity    = h;
    sensorReady = true;

    Serial.printf("Sensor OK: %.1f°C | %.1f%%\n", temperature, humidity);
    sendData();
  } else {
    sensorReady = false;
    Serial.println("SHT30 read failed.");
  }

  yield();
}

// ------------------------------------------------------------
// HTTP POST
// ------------------------------------------------------------
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
    "{\"device_id\":\"ESP_04\","
    "\"temperature\":%.1f,"
    "\"humidity\":%.1f}",
    temperature, humidity
  );

  int code = http.POST(payload);
  http.end();

  Serial.printf("HTTP POST [%d] → %s\n", code, payload);
}

// ------------------------------------------------------------
// Webserver
// ------------------------------------------------------------
void handleRoot() {
  server.send(200, "text/plain", "ESP_04 ENV Sensor OK");
}

void handleLedOn() {
  digitalWrite(ledPin, LOW);   // active LOW
  server.send(200, "text/plain", "LED ON");
}

void handleLedOff() {
  digitalWrite(ledPin, HIGH);
  server.send(200, "text/plain", "LED OFF");
}
