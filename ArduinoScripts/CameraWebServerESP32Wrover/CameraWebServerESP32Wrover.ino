#include "esp_camera.h"
#include <WiFi.h>
#include "esp_http_server.h"
#include <HardwareSerial.h>

#include "config.h"
#include "camera_pins.h"

// ===== MJPEG =====
#define BOUNDARY "frame"
static const char* STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" BOUNDARY;
static const char* STREAM_BOUNDARY     = "\r\n--" BOUNDARY "\r\n";
static const char* STREAM_PART_HEADER  = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

static httpd_handle_t compat_httpd = NULL; // :80  -> /command, /snapshot (für dein Frontend)
static httpd_handle_t stream_httpd = NULL; // :81  -> /stream, /snapshot
static httpd_handle_t ctrl_httpd   = NULL; // :82  -> /cmd

HardwareSerial ArduinoSerial(2);

static inline void send_to_arduino_line(const char* line)
{
  ArduinoSerial.print(line);
  ArduinoSerial.print('\n');
}

static bool is_cmd_safe(const char* s)
{
  // erlaubt: A-Z a-z 0-9 _ :
  for (; *s; ++s) {
    char c = *s;
    bool ok = (c >= 'a' && c <= 'z') ||
              (c >= 'A' && c <= 'Z') ||
              (c >= '0' && c <= '9') ||
              (c == '_') ||
              (c == ':');
    if (!ok) return false;
  }
  return true;
}

// -------------------- Snapshot Handler (wird auf 80 und 81 benutzt) --------------------
static esp_err_t snapshot_handler(httpd_req_t *req)
{
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Camera capture failed");
    return ESP_FAIL;
  }

  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store, no-cache, must-revalidate, max-age=0");
  httpd_resp_set_hdr(req, "Pragma", "no-cache");

  esp_err_t res = httpd_resp_send(req, (const char*)fb->buf, fb->len);
  esp_camera_fb_return(fb);
  return res;
}

// -------------------- Stream Handler (nur 81) --------------------
static esp_err_t stream_handler(httpd_req_t *req)
{
  char header_buf[64];

  httpd_resp_set_type(req, STREAM_CONTENT_TYPE);
  httpd_resp_set_hdr(req, "Cache-Control", "no-store, no-cache, must-revalidate, max-age=0");
  httpd_resp_set_hdr(req, "Pragma", "no-cache");

  while (true) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) return ESP_FAIL;

    size_t hlen = snprintf(header_buf, sizeof(header_buf), STREAM_PART_HEADER, fb->len);

    if (httpd_resp_send_chunk(req, STREAM_BOUNDARY, strlen(STREAM_BOUNDARY)) != ESP_OK ||
        httpd_resp_send_chunk(req, header_buf, hlen) != ESP_OK ||
        httpd_resp_send_chunk(req, (const char*)fb->buf, fb->len) != ESP_OK) {
      esp_camera_fb_return(fb);
      break;
    }

    esp_camera_fb_return(fb);
    delay(1);
  }

  return ESP_OK;
}

// -------------------- Control Handler (82): /cmd?c=Forward&s=200 --------------------
static esp_err_t cmd_handler(httpd_req_t *req)
{
  char query[256] = {0};
  char cbuf[64]   = {0};
  char sbuf[16]   = {0};

  if (httpd_req_get_url_query_str(req, query, sizeof(query)) != ESP_OK) {
    httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Use /cmd?c=Forward&s=200");
    return ESP_FAIL;
  }

  bool got_cmd = (httpd_query_key_value(query, "c", cbuf, sizeof(cbuf)) == ESP_OK) ||
                 (httpd_query_key_value(query, "cmd", cbuf, sizeof(cbuf)) == ESP_OK);

  if (!got_cmd) {
    httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Missing c/cmd");
    return ESP_FAIL;
  }

  if (!is_cmd_safe(cbuf)) {
    httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid chars in command");
    return ESP_FAIL;
  }

  bool has_speed = (httpd_query_key_value(query, "s", sbuf, sizeof(sbuf)) == ESP_OK) ||
                   (httpd_query_key_value(query, "speed", sbuf, sizeof(sbuf)) == ESP_OK);

  char line[96];
  if (has_speed) {
    int speed = atoi(sbuf);
    if (speed < 0) speed = 0;
    if (speed > 255) speed = 255;
    snprintf(line, sizeof(line), "%s:%d", cbuf, speed);
  } else {
    snprintf(line, sizeof(line), "%s", cbuf);
  }

  send_to_arduino_line(line);

  httpd_resp_set_type(req, "application/json");
  httpd_resp_send(req, "{\"ok\":true}", HTTPD_RESP_USE_STRLEN);
  return ESP_OK;
}

// -------------------- Compatibility Handler (80): /command?cmd=Forward --------------------
// Dein HTML macht: fetch(`http://${ESP32_IP}/command?cmd=${cmd}`)
static esp_err_t compat_command_handler(httpd_req_t *req)
{
  char query[256] = {0};
  char cmd[64]    = {0};

  if (httpd_req_get_url_query_str(req, query, sizeof(query)) != ESP_OK ||
      httpd_query_key_value(query, "cmd", cmd, sizeof(cmd)) != ESP_OK) {
    httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Use /command?cmd=Forward");
    return ESP_FAIL;
  }

  if (!is_cmd_safe(cmd)) {
    httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid chars in cmd");
    return ESP_FAIL;
  }

  // Optional: speed aus query lesen, falls du irgendwann /command?cmd=Forward&speed=200 sendest
  char sbuf[16] = {0};
  bool has_speed = (httpd_query_key_value(query, "speed", sbuf, sizeof(sbuf)) == ESP_OK);

  char line[96];
  if (has_speed) {
    int speed = atoi(sbuf);
    if (speed < 0) speed = 0;
    if (speed > 255) speed = 255;
    snprintf(line, sizeof(line), "%s:%d", cmd, speed);
  } else {
    // ohne speed -> Arduino nutzt DEFAULT_SPEED
    snprintf(line, sizeof(line), "%s", cmd);
  }

  send_to_arduino_line(line);

  // Dein JS macht response.text() -> wir geben plain text zurück
  httpd_resp_set_type(req, "text/plain");
  httpd_resp_send(req, "OK", HTTPD_RESP_USE_STRLEN);
  return ESP_OK;
}

// -------------------- Server Start Helpers --------------------
static void startCompatServer80()
{
  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.server_port = COMPAT_HTTP_PORT;
  cfg.ctrl_port   = 32768 + COMPAT_HTTP_PORT;
  cfg.stack_size  = 4096;
  cfg.max_uri_handlers = 8;
  cfg.lru_purge_enable = true;

  httpd_uri_t uri_command  = { .uri="/command",  .method=HTTP_GET, .handler=compat_command_handler, .user_ctx=NULL };
  httpd_uri_t uri_snapshot = { .uri="/snapshot", .method=HTTP_GET, .handler=snapshot_handler,       .user_ctx=NULL };

  if (httpd_start(&compat_httpd, &cfg) == ESP_OK) {
    httpd_register_uri_handler(compat_httpd, &uri_command);
    httpd_register_uri_handler(compat_httpd, &uri_snapshot);
  }
}

static void startStreamServer81()
{
  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.server_port = STREAM_HTTP_PORT;
  cfg.ctrl_port   = 32768 + STREAM_HTTP_PORT;
  cfg.stack_size  = 8192;
  cfg.max_uri_handlers = 8;
  cfg.lru_purge_enable = true;

  httpd_uri_t uri_stream   = { .uri="/stream",   .method=HTTP_GET, .handler=stream_handler,   .user_ctx=NULL };
  httpd_uri_t uri_snapshot = { .uri="/snapshot", .method=HTTP_GET, .handler=snapshot_handler, .user_ctx=NULL };

  if (httpd_start(&stream_httpd, &cfg) == ESP_OK) {
    httpd_register_uri_handler(stream_httpd, &uri_stream);
    httpd_register_uri_handler(stream_httpd, &uri_snapshot);
  }
}

static void startCtrlServer82()
{
  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.server_port = CTRL_HTTP_PORT;
  cfg.ctrl_port   = 32768 + CTRL_HTTP_PORT;
  cfg.stack_size  = 4096;
  cfg.max_uri_handlers = 8;
  cfg.lru_purge_enable = true;

  httpd_uri_t uri_cmd = { .uri="/cmd", .method=HTTP_GET, .handler=cmd_handler, .user_ctx=NULL };

  if (httpd_start(&ctrl_httpd, &cfg) == ESP_OK) {
    httpd_register_uri_handler(ctrl_httpd, &uri_cmd);
  }
}

void setup()
{
  Serial.begin(115200);
  Serial.setDebugOutput(false);

  ArduinoSerial.begin(ARDUINO_BAUD, SERIAL_8N1, ARD_RX_PIN, ARD_TX_PIN);

  // Camera config
  camera_config_t c;
  c.ledc_channel = LEDC_CHANNEL_0;
  c.ledc_timer   = LEDC_TIMER_0;

  c.pin_d0 = Y2_GPIO_NUM; c.pin_d1 = Y3_GPIO_NUM; c.pin_d2 = Y4_GPIO_NUM; c.pin_d3 = Y5_GPIO_NUM;
  c.pin_d4 = Y6_GPIO_NUM; c.pin_d5 = Y7_GPIO_NUM; c.pin_d6 = Y8_GPIO_NUM; c.pin_d7 = Y9_GPIO_NUM;

  c.pin_xclk = XCLK_GPIO_NUM;
  c.pin_pclk = PCLK_GPIO_NUM;
  c.pin_vsync = VSYNC_GPIO_NUM;
  c.pin_href = HREF_GPIO_NUM;
  c.pin_sccb_sda = SIOD_GPIO_NUM;
  c.pin_sccb_scl = SIOC_GPIO_NUM;
  c.pin_pwdn = PWDN_GPIO_NUM;
  c.pin_reset = RESET_GPIO_NUM;

  c.xclk_freq_hz = CAM_XCLK_HZ;
  c.pixel_format = PIXFORMAT_JPEG;
  c.frame_size   = CAM_FRAME_SIZE;
  c.jpeg_quality = CAM_JPEG_QUALITY;

  c.fb_count     = 2;
  c.fb_location  = CAMERA_FB_IN_PSRAM;
  c.grab_mode    = CAMERA_GRAB_LATEST;

  if (esp_camera_init(&c) != ESP_OK) {
    Serial.println("Camera init failed");
    return;
  }

  sensor_t* s = esp_camera_sensor_get();
  s->set_lenc(s, 0);
  s->set_bpc(s, 0);
  s->set_wpc(s, 0);
  s->set_dcw(s, 1);
  s->set_exposure_ctrl(s, 1);
  s->set_aec2(s, 0);
  s->set_aec_value(s, CAM_AEC_VALUE);
  s->set_gain_ctrl(s, 1);
  s->set_agc_gain(s, CAM_AGC_GAIN);

  WiFi.begin(ssid, password);
  WiFi.setSleep(false);
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }
  Serial.println();

  // Start servers
  startCompatServer80();  // <- wichtig für dein bestehendes HTML: /command, /snapshot ohne Port
  startStreamServer81();  // <- MJPEG stream
  startCtrlServer82();    // <- cmd API (optional)

  Serial.print("Compat:   http://"); Serial.print(WiFi.localIP()); Serial.println("/command?cmd=Forward");
  Serial.print("Snapshot: http://"); Serial.print(WiFi.localIP()); Serial.println("/snapshot");
  Serial.print("Stream:   http://"); Serial.print(WiFi.localIP()); Serial.print(":"); Serial.print(STREAM_HTTP_PORT); Serial.println("/stream");
  Serial.print("Cmd:      http://"); Serial.print(WiFi.localIP()); Serial.print(":"); Serial.print(CTRL_HTTP_PORT);   Serial.println("/cmd?c=Forward&s=200");
}

void loop() { delay(1000); }
