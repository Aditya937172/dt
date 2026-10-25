# ESP32 FSR stream with wireless telemetry and OTA updates

The sketch samples GPIO34 and GPIO35 at a target rate of 100 Hz. It sends raw readings by USB serial and broadcasts `VECTOR_FSR_V1,sequence,micros,GPIO34,GPIO35` packets on UDP port 8766. The laptop and ESP32 must share a trusted local network. The ESP32 also starts a backup access point; UDP telemetry is not encrypted.

## Private configuration

Copy `wifi_secrets.example.h` to `wifi_secrets.h` and set your own access-point and OTA passwords. `wifi_secrets.h` is local-only and excluded from version control. To connect the ESP32 to your home Wi-Fi, use the existing serial setup command `WIFI|network-name|network-password` once; the ESP32 saves it in flash. Do not put network passwords in this repository.

## Build and upload

Compile with the installed ESP32 Arduino core:

```powershell
.\tools\arduino-cli\arduino-cli.exe compile --fqbn esp32:esp32:esp32 --output-dir firmware\fsr_stream_ota\build firmware\fsr_stream_ota
```

For a board already running the OTA sketch, use `python tools/upload_fsr_ota.py --host ESP32_IP` while the laptop and ESP32 share a network. The script reads the OTA password from the local-only header. USB flashing also works. After a successful upload, the ESP32 restarts and resumes serial and Wi-Fi telemetry. Keep the OTA handler in any future replacement sketch if you want wireless firmware updates.

Run the dashboard with `--fsr-transport wifi` to receive UDP packets. The original USB serial mode remains the default.
