#include <WiFi.h>
#include <esp_camera.h>
#include <esp_http_server.h>

// ==================== ANPASSEN: WLAN-Zugangsdaten ====================
const char* ssid = "FRITZ!Box 7362 SL";
const char* password = "56170919150643583799";

// ==================== ANPASSEN: Kamera-Pins (AI Thinker ESP32-CAM) ====================
#define PWDN_GPIO_NUM     -1
#define RESET_GPIO_NUM    15
#define XCLK_GPIO_NUM     27
#define SIOD_GPIO_NUM     22
#define SIOC_GPIO_NUM     23
#define Y9_GPIO_NUM       19
#define Y8_GPIO_NUM       36
#define Y7_GPIO_NUM       18
#define Y6_GPIO_NUM       39
#define Y5_GPIO_NUM        5
#define Y4_GPIO_NUM       34
#define Y3_GPIO_NUM       35
#define Y2_GPIO_NUM       32
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     26
#define PCLK_GPIO_NUM     21

// ==================== Arduino-Kommunikation über Serial2 ====================
#define ARDUINO_TX_PIN 33  // TX ESP32 → RX Arduino
#define ARDUINO_RX_PIN 4   // RX ESP32 → TX Arduino

// Webserver-Handle
httpd_handle_t server = NULL;

// --------------------------------------------------------------------
// 1) WLAN-Verbindung
// --------------------------------------------------------------------
void connectToWiFi() {
  WiFi.begin(ssid, password);
  Serial.println("Verbinde mit WLAN...");
  int retryCount = 0;
  while (WiFi.status() != WL_CONNECTED && retryCount < 20) {
    delay(500);
    Serial.print(".");
    retryCount++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nVerbunden!");
    Serial.print("IP-Adresse des ESP32: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nFehler: WLAN-Verbindung fehlgeschlagen! Neustart...");
    ESP.restart();
  }
}

// --------------------------------------------------------------------
// 2) Funktion: CORS-Header setzen (Browser darf Cross-Origin zugreifen)
// --------------------------------------------------------------------
static void setCORSHeaders(httpd_req_t *req) {
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Headers", "Content-Type, Access-Control-Allow-Headers");
}

// --------------------------------------------------------------------
// 3) Snapshot-Handler (EIN Bild) mit CORS
//     - /snapshot?time=xyz
// --------------------------------------------------------------------
static esp_err_t snapshotHandler(httpd_req_t *req) {
  // Wenn Browser zuerst einen OPTIONS-Request schickt (Preflight):
  if (req->method == HTTP_OPTIONS) {
    setCORSHeaders(req);
    // Leere Antwort = 200 OK
    return httpd_resp_send(req, NULL, 0);
  }

  // Für GET-Request: CORS-Header hinzufügen
  setCORSHeaders(req);

  // Kamerabild holen
  camera_fb_t * fb = esp_camera_fb_get();
  if(!fb) {
    httpd_resp_send_500(req);
    return ESP_FAIL;
  }

  // MIME-Type: JPEG
  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Content-Disposition", "inline; filename=capture.jpg");

  // Bilddaten senden
  esp_err_t res = httpd_resp_send(req, (const char*)fb->buf, fb->len);
  esp_camera_fb_return(fb);

  return res;
}

// --------------------------------------------------------------------
// 4) Command-Handler (cmd=LED_AN etc.) mit CORS
//     - /command?cmd=LED_AN
// --------------------------------------------------------------------
static esp_err_t commandHandler(httpd_req_t *req) {
  // Preflight-Anfrage?
  if (req->method == HTTP_OPTIONS) {
    setCORSHeaders(req);
    return httpd_resp_send(req, NULL, 0); // Leer, 200 OK
  }

  // CORS-Header setzen für GET/POST
  setCORSHeaders(req);

  // URL-Parameter auslesen
  char buf[100];
  if (httpd_req_get_url_query_str(req, buf, sizeof(buf)) == ESP_OK) {
    char command[50];
    // Suche nach cmd=...
    if (httpd_query_key_value(buf, "cmd", command, sizeof(command)) == ESP_OK) {
      // Befehl an Arduino
      Serial2.println(command);

      // Debug
      Serial.print("Befehl an Arduino gesendet: ");
      Serial.println(command);

      // Antwort an Browser
      const char* resp_str = "Befehl gesendet";
      httpd_resp_send(req, resp_str, strlen(resp_str));
      return ESP_OK;
    }
  }
  
  // Fallback, falls kein cmd gefunden
  httpd_resp_send(req, "Fehler: Kein Befehl gefunden", strlen("Fehler: Kein Befehl gefunden"));
  return ESP_FAIL;
}

// --------------------------------------------------------------------
// 5) Webserver starten (Port 80)
// --------------------------------------------------------------------
void startCameraServer() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 80;

  if (httpd_start(&server, &config) == ESP_OK) {
    // /snapshot
    httpd_uri_t snapshot_uri = {
      .uri       = "/snapshot",
      .method    = HTTP_GET,  // Wir behandeln OPTIONS manuell im Handler
      .handler   = snapshotHandler,
      .user_ctx  = NULL
    };
    httpd_register_uri_handler(server, &snapshot_uri);

    // /command
    httpd_uri_t command_uri = {
      .uri       = "/command",
      .method    = HTTP_GET,
      .handler   = commandHandler,
      .user_ctx  = NULL
    };
    httpd_register_uri_handler(server, &command_uri);

    Serial.println("HTTP-Server gestartet.");
  }
}

// --------------------------------------------------------------------
// 6) setup(): WLAN, Kamera, Serial2, Server
// --------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  Serial.println("Starte ESP32-CAM...");

  // UART2 für Arduino
  Serial2.begin(9600, SERIAL_8N1, ARDUINO_TX_PIN, ARDUINO_RX_PIN);
  Serial.println("Serial2 gestartet (Pins TX=33, RX=4).");

  // WLAN
  connectToWiFi();

  // Kamera-Konfiguration
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // Höhere Einstellungen, falls PSRAM vorhanden
  if (psramFound()) {
    config.frame_size = FRAMESIZE_VGA;  // 640x480
    config.jpeg_quality = 10;          // 10 = hohe Qualität
    config.fb_count = 2;
  } else {
    config.frame_size = FRAMESIZE_CIF; // 352x288
    config.jpeg_quality = 12; 
    config.fb_count = 1;
  }

  // Kamera initialisieren
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Kamera init fehlgeschlagen. Fehler: 0x%x\n", err);
    return;
  }

  // HTTP-Server starten
  startCameraServer();
}

// --------------------------------------------------------------------
// 7) loop(): Empfange ggfs. Rückmeldungen vom Arduino
// --------------------------------------------------------------------
void loop() {
  if (Serial2.available()) {
    String msg = Serial2.readStringUntil('\n');
    Serial.print("Arduino -> ESP32: ");
    Serial.println(msg);
  }
}
