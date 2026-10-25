# Camo MediaPipe Hand Capture

## Wireless FSR telemetry

The ESP32 OTA sketch now broadcasts each raw FSR sample as a local UDP datagram on port 8766. It keeps the 115200-baud USB serial stream as a fallback. The Wi-Fi packet is `VECTOR_FSR_V1,sequence,esp_micros,gpio34_adc,gpio35_adc` at a target rate of 100 Hz. The laptop records the ESP32 timestamp and its own packet receive time; UDP packet gaps are counted in the live FSR status. This is local-network telemetry, not an Internet or cloud upload.

1. Compile and upload `firmware/fsr_stream_ota/fsr_stream_ota.ino` to the ESP32. The existing OTA update process is described in `firmware/fsr_stream_ota/README.md`; USB flashing also works. The ESP32 must be running the new build before Wi-Fi data can appear.
2. Put the ESP32 and laptop on the same Wi-Fi network. The sketch also broadcasts to laptops joined to its backup access point. Power the ESP32 through a power bank when untethered.
3. Start the dashboard in Wi-Fi mode:

```powershell
.\.python312\python.exe -m app.main --camera 0 --camera-backend msmf --max-camera-index 0 --camera-label CAMO --web --port 8003 --fsr-transport wifi
```

Open `http://localhost:8003`. The FSR card should change from **NO WIFI DATA** to **LIVE · WI-FI** and show raw GPIO34/GPIO35 counts. If Windows asks, allow the Python receiver to accept UDP on port 8766 on the private network. A router's client-isolation setting or a public-network firewall can prevent local broadcasts. To use the original USB data path, omit `--fsr-transport wifi` (or set it to `serial`). The existing physical FSR1 fault still prevents reliable two-pad pressure calibration; Wi-Fi changes transport, not sensor quality. ToF remains disabled.

## Session database and replay

The live workspace at `http://localhost:8003` now has a pressure timeline and a session picker. **Record** saves the camera, tracked hand, robot hand, and every ESP32 FSR sample. **Stop** finalizes the MP4; choose the session from the timeline picker to scrub or play it back. The 3D scene, raw sensor numbers, and event labels follow the recorded session. The browser's simulated-pressure toggle is clearly labeled and never writes fake samples into the database.

Each recording produces `sessions/session_NNN/` with `camera.mp4`, `video_frames.jsonl`, `hand_landmarks.jsonl`, `robot_hand_state.jsonl`, `fsr.jsonl`, `events.jsonl`, `metadata.json`, and `calibration.json`. A central SQLite database at `sessions/captures.sqlite` indexes the same data in `sessions`, `frames`, `fsr_samples`, `events`, and `video_frames` tables. `fsr_samples` stores every raw GPIO34/GPIO35 packet, its ESP32 microsecond timestamp, and its PC monotonic receive time in the application's `session_time_ms` timeline. Calibrated rows also contain nullable `thumb_pressure` and `index_pressure` values plus a quality flag; uncalibrated rows retain only raw ADC values. The video frame index maps MP4 frames to that same timeline. The raw JSONL files remain readable without SQLite.

Pressure calibration requires two deliberate steps with the ESP32 connected: leave both pads untouched for at least one second and click **Set untouched baseline**; then press and hold both pads and click **Set both pressed range**. The app rejects a low/unstable released baseline and does not infer grasp events until both calibration steps succeed. Pressure values are relative, never newtons. An uncalibrated session still records the raw ADC stream and replay labels it **RAW REPLAY**. If both channels stay near zero, the UI marks **CHECK SIGNAL**, because a loose shared power feed previously produced that reading. Check wiring before interpreting it as contact.

The visual grasp labels are inferred from hand landmarks and calibrated pressure with hysteresis; they are not physical force or collision measurements. The 3D scene shows hands only. ToF remains disabled.

Run the workspace with Camo when its live camera feed is available:

```powershell
.\.python312\python.exe -m app.main --camera 0 --camera-backend msmf --max-camera-index 0 --camera-label CAMO --web --port 8003
```

Inspect the database from Python:

```powershell
.\.python312\python.exe -c "import sqlite3; db=sqlite3.connect('sessions/captures.sqlite'); print(db.execute('SELECT id,frame_count FROM sessions ORDER BY id DESC LIMIT 5').fetchall()); db.close()"
```

## Vision and pressure workspace

The live workspace tracks hands and fingers, renders anatomical hands, and shows the ESP32 FSR readings. Shoulder and elbow tracking are disabled. Start it with:

```powershell
.\.python312\python.exe -m app.main --camera 0 --camera-backend msmf --max-camera-index 0 --camera-label CAMO --web --port 8003
```

Open `http://localhost:8003`. Keep both hands visible in Camo. Hand placement follows camera coordinates directly; the optional grid is off by default. The FSR card shows raw GPIO34/35 readings from COM7. It shows relative pressure and inferred grasp events only after the two calibration steps succeed. Use `--no-fsr` if the ESP32 is disconnected.

For a presentation while the sensor wiring is being repaired, open `http://localhost:8003/?demo=1`. This enables **Simulated pressure demo** with two manual sliders. The FSR panel and fingertip highlights respond to slider movement and are labeled **SIMULATED**. Turn the toggle off to return to actual ESP32 readings. Demo values are only in the browser and are not recorded as hardware data.

Shoulder and elbow inference has been removed from the live pipeline. The camera and ESP32 must be tested with real movement and pressure before using the readings for calibrated grasp behavior.

Low-latency hand tracking for an iPhone exposed as a Windows camera through Camo Studio. The local Three.js workspace shows anatomical hands and live ESP32 FSR telemetry. It does not use ToF, object detection, cloud upload, or a physics simulator.

## Live 3D Workspace

```powershell
.\.python312\python.exe -m app.main --camera 0 --camera-backend msmf --max-camera-index 0 --camera-label CAMO --web --port 8003
```

On this laptop, OpenCV camera index 0 is Camo and index 1 is the integrated webcam. Media Foundation (`--camera-backend msmf`) supplied live frames after DirectShow returned black frames on a restart. If both backends return black while Studio shows a live picture, reconnect the iPhone in Camo Studio and recheck the site.

```powershell
.\.python312\python.exe -m app.main --camera 0 --camera-backend msmf --max-camera-index 0 --camera-label CAMO --web --port 8003
```

Open http://localhost:8003. Keep Camo Studio connected. The OpenCV window and its R/S/Q controls continue working; browser Record/Stop controls use the same recorder. Close the earlier capture process before starting another process on the same camera.

Three.js, OrbitControls, and Lucide assets are vendored under `web/vendor`; the running page needs no internet. Camera preview comes from the same Python pipeline, not a second browser camera session.

The WebSocket requests one newest state per render, with one response in flight. Raw landmarks remain unchanged; `robot_hands` contains smoothed workspace geometry, all 21 points, per-finger joints, wrist translation, and palm orientation. Position EMA alpha is 0.82 for lower lag; rotation is smoothed and orthonormalized. The retargeter maps every image landmark onto a shared scene plane, preserving apparent hand size and placement. Lost tracking hides the model; stale/disconnected states are also flagged. OrbitControls rotates the viewing camera independently of tracking.

`robot_hand_state.jsonl` is saved beside `hand_landmarks.jsonl` for every recorded frame, including empty-hand frames, with matching frame IDs and timestamps. The live state includes hand landmarks and FSR telemetry. Orientation is a column-major 3x3 rotation matrix, and all positions are visual workspace units, not meters. Palm size gives a bounded relative-depth cue; MediaPipe Z adds approximate articulation depth. Handedness confidence is a classification score, not a camera-quality score.

State age measures publication-to-render delay after inference, using an initial local clock-offset handshake. It excludes sensor/Camo latency and EMA lag, and is not an end-to-end latency measurement. Both hands render; the curl panel shows the first detected hand. Handedness flips or two hands with the same label can reset/swap smoothing identity.

Verification: ` .\.python312\python.exe -m unittest discover -s tests `. These synthetic geometry tests do not replace physical gesture checks.

## Setup

Install Python 3.11 or 3.12, then from this folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

For this workspace, a portable Python 3.12 runtime has already been set up at `.python312`, so you can also run:

```powershell
.\.python312\python.exe -m app.main --list-cameras
.\.python312\python.exe -m app.main --camera 0
```

The app downloads `models/hand_landmarker.task` on first run if it is missing.

## Camera Discovery

```powershell
python -m app.main --list-cameras
```

OpenCV on Windows can probe camera indices reliably, but it cannot always map DirectShow device names to those indices. If Camo is not selected automatically, choose the index manually:

```powershell
python -m app.main --camera 0
```

## Run

```powershell
python -m app.main --camera 0 --width 1280 --height 720 --fps 30
```

Controls:

- `R`: start recording landmark JSONL
- `S`: stop recording
- `Q`: quit

Recordings are written to:

```text
sessions/session_001/hand_landmarks.jsonl
sessions/session_001/metadata.json
```

Each JSONL row uses monotonic session timestamps:

```json
{
  "timestamp_ms": 123456,
  "frame_id": 829,
  "hands": [
    {
      "handedness": "Right",
      "landmarks": [
        {"id": 0, "x": 0.51, "y": 0.72, "z": -0.01}
      ]
    }
  ]
}
```

## Notes

- The preview is mirrored horizontally for natural movement.
- Coordinates are normalized from `0.0` to `1.0`.
- Finger curl values are angle-based approximations where `0.0` is extended and `1.0` is strongly curled.
- The app requests `1280x720@30fps`, prints the actual OpenCV capture resolution, and shows measured FPS in the preview.


