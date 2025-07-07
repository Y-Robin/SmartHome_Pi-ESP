#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ESP8266HTTPClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>
extern "C" {
  #include "user_interface.h"
}
#include "config.h"

// --- Pins & Setup ---
const int ledPin = D1;
#define ONE_WIRE_BUS D3  // Sensor an D3 (GPIO0)
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

ESP8266WebServer server(80);

// --- Sensor & Timing ---
float temperature = NAN;
bool sensorReady = false;

unsigned long lastReadTime = 0;
unsigned long lastRetryTime = 0;
unsigned long lastMemLog = 0;
const unsigned long readInterval = 100000;     // 100 s bei gültigem Sensor
const unsigned long retryInterval = 5000;      // 5 s bei Sensorfehler
const unsigned long memLogInterval = 60000;    // 1 Min Heap-Log
const unsigned long rebootThreshold = 3000;    // min. 3 KB Heap vor Reboot

void setup() {
  Serial.begin(115200);
  Serial.println("\nBooting...");

  pinMode(ledPin, OUTPUT);
  sensors.begin();

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
  server.begin();
}

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
  sensors.requestTemperatures();
  float t = sensors.getTempCByIndex(0);

  if (t != DEVICE_DISCONNECTED_C) {
    temperature = t;
    sensorReady = true;
    Serial.printf("Sensor OK: %.1f°C\n", temperature);
    sendData();
  } else {
    sensorReady = false;
    Serial.println("DS18B20 read failed.");
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
           "{\"device_id\":\"ESP_02\",\"temperature\":%.1f,\"humidity\":%.1f}",
           temperature, 50.0);  // Dummy Humidity

  int code = http.POST(payload);
  http.end();

  Serial.printf("HTTP POST [%d] → %s\n", code, payload);
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
