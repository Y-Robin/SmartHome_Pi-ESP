#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ESP8266HTTPClient.h>
#include <DHT.h>
#include <AccelStepper.h>
#include "config.h"


// Stepper motor pins and settings
const int motorPin1 = D5; // Define motor control pins
const int motorPin2 = D6;
const int motorPin3 = D7;
const int motorPin4 = D8;
AccelStepper stepper(AccelStepper::FULL4WIRE, motorPin1, motorPin3, motorPin2, motorPin4);


// Set the GPIO pin where you have connected your LED or relay
const int ledPin = D1;
#define DHTPIN D2  // Change to the pin you connected DHT
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

ESP8266WebServer server(80);  // Create a web server on port 80

// Variables for stepper control
int currentAngle = 0;
int targetAngle = 0;

void setup() {
  Serial.begin(115200);

  stepper.setMaxSpeed(100); // Set the maximum speed
  stepper.setAcceleration(100); // Set the acceleration
  
  // Initialize the LED pin as an output
  pinMode(ledPin, OUTPUT);
  dht.begin(); 
  // Connect to WiFi
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("");
  Serial.print("Connected to WiFi. IP address: ");
  Serial.println(WiFi.localIP());

  // Define web server routes
  server.on("/", handleRoot);      // Call the 'handleRoot' function when a client requests URI "/"
  server.on("/on", handleLedOn);   // Call 'handleLedOn' when a client requests URI "/on"
  server.on("/off", handleLedOff); // Call 'handleLedOff' when a client requests URI "/off"
  server.on("/set_angle", HTTP_GET, setAngle);
  server.on("/get_angle", HTTP_GET, getAngle);

  server.begin(); // Start the server
}

void loop() {
  server.handleClient(); // Handle client requests
  handleStepperMovement();

  //Serial.println(humidity);
  // Send temperature data to Flask server every 10 seconds
  static unsigned long lastTime = 0;
  if (millis() - lastTime > 100000) {
    float humidity = dht.readHumidity();
    float temperature = dht.readTemperature();

    if (isnan(humidity) || isnan(temperature)) {
      Serial.println("Failed to read from DHT sensor!");
      delay(100);
      return;
    }
    lastTime = millis();
    if (WiFi.status() == WL_CONNECTED) {
      WiFiClient client;
      HTTPClient http;
      http.begin(client, serverUrl);
      
      http.addHeader("Content-Type", "application/json");
      String payload = "{\"device_id\": \"ESP_01\", \"temperature\": " + String(temperature) + ", \"humidity\": " + String(humidity) + "}";
      http.POST(payload);
      http.end();
      Serial.println(payload);
    }
  }
}

void handleRoot() {
  server.send(200, "text/plain", "ESP8266 LED Control");
}

void handleLedOn() {
  digitalWrite(ledPin, HIGH);  // Turn the LED on
  server.send(200, "text/plain", "LED is ON");
}

void handleLedOff() {
  digitalWrite(ledPin, LOW);   // Turn the LED off
  server.send(200, "text/plain", "LED is OFF");
}

void setAngle() {
  Serial.println(server.arg("angle"));
  if (server.arg("angle") != "") {
    targetAngle = server.arg("angle").toInt()*2000/360;
    server.send(200, "text/plain", "Angle set to: " + String(targetAngle));
  } else {
    server.send(400, "text/plain", "Missing angle parameter");
  }
}

void getAngle() {
  server.send(200, "text/plain", String(currentAngle));
}

void handleStepperMovement() {
  if (stepper.distanceToGo() == 0) {
    stepper.moveTo(targetAngle);
  }
  stepper.run();
  currentAngle = stepper.currentPosition();
}