# Smart Home System with Raspberry Pi and ESP Modules

## Overview

This smart home system integrates various functionalities such as camera streaming, temperature monitoring, and stepper motor control using a Raspberry Pi, ESP8266, and ESP32-CAM modules. It features a web-based interface with several tabs to control and monitor different aspects of the system. The repository includes programs for all ESP modules used in this project.

## Features

### Webpages

1. **Home**: Displays all connected ESP8266 devices, their current status, and peripherals.
   ![Home Page](Images/Index.png)
2. **Camera**: Live stream from the Raspberry Pi camera with recording capabilities.
   ![Camera Page](Images/Camera1.png)
3. **ESP Stream**: Live stream from ESP32-CAM. (Recording not available)
   ![ESP Stream Page](Images/Camera2.png)
4. **Temperature Bad**: Shows temperature data from connected sensors.
   ![Temperature Page](Images/Temperatur.png)
5. **Stepper Motor Control**: Password-protected control for a stepper motor connected to an ESP8266.
   ![Stepper Motor Control Page](Images/Stepper.png)
6. **Video Library**: View all recorded videos from the Pi camera.
   ![Video Library Page](Images/VideoLib.png)
7. **Robot**: View all recorded videos from the Pi camera.
   ![Video Library Page](Images/VideoLib.png)

### Hardware

- Raspberry Pi 4B
- ESP8266 Modules: [ESP8266 NodeMCU CP2102](https://www.amazon.de/dp/B08HQ9991S?psc=1&ref=ppx_yo2ov_dt_b_product_details)
- ESP32-CAM Module
- Raspberry Pi Camera Module: [Purchase Link](https://www.amazon.de/kamera-Raspberry-Kamera-geh%C3%A4use-Flexkabel/dp/B07MNR3VM8/ref=sr_1_11?__mk_de_DE=%C3%85M%C3%85%C5%BD%C3%95%C3%91&keywords=pi+camera&qid=1700404319&sr=8-11)
- Peripherals: LED, DHT11 Sensor, Stepper Motor with Shield


### Setup

#### Python Libraries Installation
To set up your environment, you need to install the following Python libraries:
```python 
pip install Flask
pip install flask_socketio
pip install flask_sqlalchemy
pip install requests
pip install flask_httpauth
pip install opencv-python
pip install numpy
pip install Pillow
pip install picamera
pip install tflite
```
#### Hardware and Software Setup
##### 1. Raspberry Pi Setup:
	- Attach the Raspberry Pi Camera Module.
	- Follow the instructions for software setup and dependencies.
##### 2. ESP Modules Setup:
	- Connect the LED and DHT11 Sensor to the ESP8266. Connect the stepper motor to the appropriate pins (LED: D1; Temperature: D2; Stepper: D5-D8 (5V supply)).
	- Flash the ESP32-CAM and ESP8266 with the required firmware from this repository.
![ESP-Cam Setup](Images/ESP32-Cam.jpg)
![ESP-Cam Setup](Images/ESP8266_Full.jpg)
##### 3. Network Configuration:
	- Ensure all devices are connected to the same local network (Arduino config.sh (Example is given)).
 	- Ensure all IP addresses are adapted to your local network config.yaml. An example is given.

##### Running the System
To start the system, navigate to the git folder and execute the following command:

```bash 
python app.py
```

### Usage

- Home Tab: Check the status of all connected devices and view the connected peripherals.
- Camera Tab: View the live stream from the Pi camera. Use the 'Record' button to start/stop recording.
- ESP Stream Tab: View the live stream from the ESP32-CAM.
- Temperature Tab: Select a device and date to view historical temperature data.
- Stepper Motor Tab: Control the stepper motor using the slider (password-protected access).
- Video Library Tab: Browse and view recorded videos.

### Contributing
Feedback and contributions to this project are welcome. Please submit issues and pull requests through the project's GitHub page.
