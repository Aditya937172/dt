"""Upload the compiled FSR sketch to the ESP32's existing local OTA endpoint."""

from __future__ import annotations

import argparse
import base64
import re
import secrets
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent.parent
LOCAL_CONFIG = ROOT / "firmware" / "fsr_stream_ota" / "wifi_secrets.h"
FIRMWARE = ROOT / "firmware" / "fsr_stream_ota" / "build" / "fsr_stream_ota.ino.bin"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="ESP32 IP on the local network")
    args = parser.parse_args()
    if not LOCAL_CONFIG.exists():
        raise SystemExit("Create wifi_secrets.h from wifi_secrets.example.h before uploading")
    match = re.search(r'constexpr char UPDATE_PASSWORD\[\] = "([^"]+)"', LOCAL_CONFIG.read_text())
    if not match:
        raise SystemExit("OTA password is missing from wifi_secrets.h")
    firmware = FIRMWARE.read_bytes()
    boundary = "----fsr-ota-" + secrets.token_hex(12)
    body = (f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="update"; filename="fsr_stream_ota.ino.bin"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n").encode() + firmware + f"\r\n--{boundary}--\r\n".encode()
    credentials = base64.b64encode(f"admin:{match.group(1)}".encode()).decode()
    request = Request(f"http://{args.host}/update", data=body, method="POST",
                      headers={"Authorization": f"Basic {credentials}",
                               "Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urlopen(request, timeout=90) as response:
        result = response.read(512).decode("utf-8", errors="replace")
        if response.status != 200 or "Update Success" not in result:
            raise SystemExit(f"ESP32 OTA response was not successful: HTTP {response.status}")
    print(f"ESP32 OTA accepted {len(firmware)} firmware bytes; waiting for reboot")


if __name__ == "__main__":
    main()
