#include <ESP8266WiFi.h>

#include <ESP8266WebServer.h>

#include <ESP8266HTTPClient.h>

#include <DHT.h>

#include "config.h"

// Set the GPIO pin where you have connected your LED or relay

const int ledPin = D1;

#define DHTPIN D2  // Change to the pin you connected DHT

#define DHTTYPE DHT11



DHT dht(DHTPIN, DHTTYPE);




ESP8266WebServer server(80);  // Create a web server on port 80



void setup() {

  Serial.begin(115200);

  

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



  server.begin(); // Start the server

}



void loop() {

  server.handleClient(); // Handle client requests

  float humidity = dht.readHumidity();

  float temperature = dht.readTemperature();



  if (isnan(humidity) || isnan(temperature)) {

    Serial.println("Failed to read from DHT sensor!");

    return;

  }

  //Serial.println(humidity);

  // Send temperature data to Flask server every 10 seconds

  static unsigned long lastTime = 0;

  if (millis() - lastTime > 10000) {

    lastTime = millis();

    if (WiFi.status() == WL_CONNECTED) {

      WiFiClient client;

      HTTPClient http;

      http.begin(client, serverUrl);

      

      http.addHeader("Content-Type", "application/json");

      String payload = "{\"device_id\": \"ESP_02\", \"temperature\": " + String(temperature) + ", \"humidity\": " + String(humidity) + "}";

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
