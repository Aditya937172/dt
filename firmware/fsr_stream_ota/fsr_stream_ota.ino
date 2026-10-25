#include <WiFi.h>
#include <WiFiUdp.h>
#include <WebServer.h>
#include <HTTPUpdateServer.h>
#include <ArduinoOTA.h>
#include <Preferences.h>
#include "wifi_secrets.h"

// Connect your PC to this Wi-Fi network to update the ESP32 later.

constexpr int FSR1_PIN = 34;
constexpr int FSR2_PIN = 35;
constexpr uint32_t SAMPLE_PERIOD_US = 10000;
constexpr uint16_t FSR_UDP_PORT = 8766;

WebServer webServer(80);
HTTPUpdateServer webUpdater;
WiFiUDP fsrUdp;
Preferences wifiPrefs;
uint32_t nextSampleUs;
uint32_t sampleSequence = 0;
String serialCommand;
bool homeConnectedReported = false;

void connectSavedWiFi() {
  String ssid = wifiPrefs.getString("ssid", "");
  String password = wifiPrefs.getString("password", "");
  if (ssid.length()) {
    WiFi.begin(ssid.c_str(), password.c_str());
    Serial.print("Connecting to home Wi-Fi: ");
    Serial.println(ssid);
  }
}

void readWiFiSetupCommand() {
  while (Serial.available()) {
    char ch = (char)Serial.read();
    if (ch == '\r') continue;
    if (ch == '\n') {
      if (serialCommand.startsWith("WIFI|")) {
        int split = serialCommand.indexOf('|', 5);
        if (split > 5) {
          String ssid = serialCommand.substring(5, split);
          String password = serialCommand.substring(split + 1);
          wifiPrefs.putString("ssid", ssid);
          wifiPrefs.putString("password", password);
          WiFi.begin(ssid.c_str(), password.c_str());
          homeConnectedReported = false;
          Serial.print("Connecting to home Wi-Fi: ");
          Serial.println(ssid);
        }
      }
      serialCommand = "";
    } else if (serialCommand.length() < 128) {
      serialCommand += ch;
    } else {
      serialCommand = "";
    }
  }
}

// Each datagram is one sample: VECTOR_FSR_V1,sequence,micros,GPIO34,GPIO35.
// Broadcast to the home network and to clients of the ESP32 backup access point.
void broadcastFsrSample(uint32_t stamp, int fsr1, int fsr2) {
  char packet[72];
  const int length = snprintf(packet, sizeof(packet), "VECTOR_FSR_V1,%lu,%lu,%d,%d",
                              (unsigned long)sampleSequence++, (unsigned long)stamp, fsr1, fsr2);
  if (length <= 0 || length >= (int)sizeof(packet)) return;

  if (WiFi.status() == WL_CONNECTED) {
    const IPAddress local = WiFi.localIP();
    const IPAddress mask = WiFi.subnetMask();
    const IPAddress broadcast(local[0] | (uint8_t)~mask[0], local[1] | (uint8_t)~mask[1],
                              local[2] | (uint8_t)~mask[2], local[3] | (uint8_t)~mask[3]);
    if (fsrUdp.beginPacket(broadcast, FSR_UDP_PORT)) {
      fsrUdp.write((const uint8_t *)packet, length);
      fsrUdp.endPacket();
    }
  }
  if (WiFi.softAPgetStationNum() > 0) {
    const IPAddress ap = WiFi.softAPIP();  // Default ESP32 AP uses a /24 subnet.
    const IPAddress broadcast(ap[0], ap[1], ap[2], 255);
    if (fsrUdp.beginPacket(broadcast, FSR_UDP_PORT)) {
      fsrUdp.write((const uint8_t *)packet, length);
      fsrUdp.endPacket();
    }
  }
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  analogSetPinAttenuation(FSR1_PIN, ADC_11db);
  analogSetPinAttenuation(FSR2_PIN, ADC_11db);

  wifiPrefs.begin("ota-wifi", false);
  WiFi.mode(WIFI_AP_STA);
  if (!WiFi.softAP(AP_NAME, AP_PASSWORD)) {
    Serial.println("Failed to start OTA Wi-Fi access point");
  }
  connectSavedWiFi();

  webServer.on("/", HTTP_GET, []() {
    webServer.send(200, "text/plain", "ESP32 FSR stream is running. Wi-Fi OTA test passed. Open /update to upload firmware.");
  });
  webUpdater.setup(&webServer, "/update", UPDATE_USER, UPDATE_PASSWORD);
  webServer.begin();
  fsrUdp.begin(0);

  ArduinoOTA.setHostname("esp32-fsr-ota");
  ArduinoOTA.setPassword(UPDATE_PASSWORD);
  ArduinoOTA.begin();

  Serial.print("OTA Wi-Fi: ");
  Serial.println(AP_NAME);
  Serial.print("OTA address: http://");
  Serial.print(WiFi.softAPIP());
  Serial.println("/update");
  nextSampleUs = micros() + SAMPLE_PERIOD_US;
}

void loop() {
  readWiFiSetupCommand();
  ArduinoOTA.handle();
  webServer.handleClient();

  if (!homeConnectedReported && WiFi.status() == WL_CONNECTED) {
    homeConnectedReported = true;
    Serial.print("HOME_WIFI_IP: ");
    Serial.println(WiFi.localIP());
  }

  const uint32_t now = micros();
  if ((int32_t)(now - nextSampleUs) < 0) return;
  const uint32_t stamp = now;
  nextSampleUs += SAMPLE_PERIOD_US;
  if ((int32_t)(now - nextSampleUs) >= 0) nextSampleUs = now + SAMPLE_PERIOD_US;
  const int fsr1 = analogRead(FSR1_PIN);
  const int fsr2 = analogRead(FSR2_PIN);
  Serial.printf("S,%lu,%d,%d\n", (unsigned long)stamp, fsr1, fsr2);
  broadcastFsrSample(stamp, fsr1, fsr2);
}
