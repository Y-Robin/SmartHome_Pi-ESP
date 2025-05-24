#include <Arduino.h>
#include <avr/wdt.h>

// Deine Libraries – Pfade ggf. anpassen:
#include "DeviceDriverSet_xxx0.h"
#include "ApplicationFunctionSet_xxx0.cpp"

// Globale Objekte für Motor-/Roboter-Funktionen
DeviceDriverSet_Motor AppMotor;
Application_xxx Application_SmartRobotCarxxx0;

void setup() {
  // Serielle Schnittstelle für Debug und empfangene Befehle
  Serial.begin(9600);

  // Hardware für die Motoren initialisieren
  AppMotor.DeviceDriverSet_Motor_Init();

  delay(100);
  Serial.println("Arduino SetupFinished");
}

void loop() {
  // Wenn Daten vom ESP32 ankommen
  if (Serial.available() > 0) {
    // Komplette Zeile bis zum Zeilenumbruch einlesen
    String command = Serial.readStringUntil('\n');
    command.trim(); // Whitespace/Newline entfernen
    
    // Debug-Ausgabe
    Serial.print("Empfangener Befehl: ");
    Serial.println(command);

    // Befehle vergleichen und entsprechende Funktion aufrufen
    if (command == "Forward") {
      // Vorwärts
      ApplicationFunctionSet_SmartRobotCarMotionControl(0, 200);
      Serial.println("Fahrbefehl: Forward");
    }
    else if (command == "Backward") {
      // Rückwärts
      ApplicationFunctionSet_SmartRobotCarMotionControl(1, 200);
      Serial.println("Fahrbefehl: Backward");
    }
    else if (command == "Left") {
      // Links drehen
      ApplicationFunctionSet_SmartRobotCarMotionControl(2, 200);
      Serial.println("Fahrbefehl: Left");
    }
    else if (command == "Right") {
      // Rechts drehen
      ApplicationFunctionSet_SmartRobotCarMotionControl(3, 200);
      Serial.println("Fahrbefehl: Right");
    }
    else if (command == "LeftForward") {
      // Schräg links-vorwärts
      ApplicationFunctionSet_SmartRobotCarMotionControl(4, 200);
      Serial.println("Fahrbefehl: LeftForward");
    }
    else if (command == "LeftBackward") {
      // Schräg links-rückwärts
      ApplicationFunctionSet_SmartRobotCarMotionControl(5, 200);
      Serial.println("Fahrbefehl: LeftBackward");
    }
    else if (command == "RightForward") {
      // Schräg rechts-vorwärts
      ApplicationFunctionSet_SmartRobotCarMotionControl(6, 200);
      Serial.println("Fahrbefehl: RightForward");
    }
    else if (command == "RightBackward") {
      // Schräg rechts-rückwärts
      ApplicationFunctionSet_SmartRobotCarMotionControl(7, 200);
      Serial.println("Fahrbefehl: RightBackward");
    }
    else if (command == "stop_it") {
      // Stopp
      ApplicationFunctionSet_SmartRobotCarMotionControl(8, 200);
      Serial.println("Fahrbefehl: stop_it");
    }
    else {
      // Unbekannter Befehl
      Serial.print("Unbekannter Befehl: ");
      Serial.println(command);
    }
  }
}
