"""Read the real ESP32 FSR stream and report raw channel statistics."""
import argparse
import statistics
import time

import serial


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--warmup", type=float, default=1.0,
                        help="Seconds to discard after serial open/ESP32 reset")
    args = parser.parse_args()
    rows = []
    with serial.Serial(args.port, 115200, timeout=0.2) as device:
        warmup_end = time.perf_counter() + args.warmup
        while time.perf_counter() < warmup_end:
            device.readline()
        device.reset_input_buffer()
        start = time.perf_counter()
        last_display = start
        while time.perf_counter() - start < args.seconds:
            line = device.readline().decode("ascii", errors="ignore").strip()
            parts = line.split(",")
            if len(parts) != 4 or parts[0] != "S":
                continue
            try:
                stamp, fsr1, fsr2 = map(int, parts[1:])
            except ValueError:
                continue
            if not 0 <= fsr1 <= 4095 or not 0 <= fsr2 <= 4095:
                continue
            rows.append((stamp, fsr1, fsr2))
            now = time.perf_counter()
            if now - last_display >= 0.2:
                rate = len(rows) / max(now - start, 0.001)
                print(f"FSR1 RAW: {fsr1:4d}  FSR2 RAW: {fsr2:4d}  RATE: {rate:5.1f} Hz", flush=True)
                last_display = now
    if not rows:
        print("No valid sensor packets")
        return 1
    for index, name in ((1, "FSR1"), (2, "FSR2")):
        values = [row[index] for row in rows]
        print(f"{name}: median={statistics.median(values):.1f} min={min(values)} max={max(values)}")
    if len(rows) > 1:
        elapsed_us = (rows[-1][0] - rows[0][0]) & 0xFFFFFFFF
        print(f"Packets={len(rows)} ESP rate={(len(rows)-1)*1e6/elapsed_us:.2f} Hz")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
