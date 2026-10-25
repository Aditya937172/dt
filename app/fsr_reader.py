"""Nonblocking USB serial or local Wi-Fi FSR reader.

Raw ADC readings are never treated as calibrated force.
"""
from __future__ import annotations

import statistics
import socket
import threading
import time
from collections import deque

import serial


class FSRReader:
    WIFI_PACKET_PREFIX = "VECTOR_FSR_V1"

    def __init__(self, port: str = "COM7", *, transport: str = "serial",
                 wifi_port: int = 8766) -> None:
        if transport not in ("serial", "wifi"):
            raise ValueError("transport must be 'serial' or 'wifi'")
        if not 1 <= wifi_port <= 65535:
            raise ValueError("wifi_port must be between 1 and 65535")
        self.port = port
        self.transport = transport
        self.wifi_port = wifi_port
        self.source_ip: str | None = None
        self.last_sequence: int | None = None
        self.wifi_missed_packets = 0
        self.lock = threading.Lock()
        self.samples: deque[tuple[int, int]] = deque(maxlen=100)
        self.pending: deque[dict] = deque(maxlen=10000)
        self.dropped_samples = 0
        self.latest: tuple[int, int] | None = None
        self.baseline: tuple[float, float] | None = None
        self.pressed: tuple[float, float] | None = None
        self.baseline_source = "none"
        self.calibration_error = "Set untouched baseline, then press both pads and set pressed range"
        self.last_sample = 0.0
        self.connected = False
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._read_wifi if transport == "wifi" else self._read_serial,
                                       daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _ingest(self, stamp: int, values: tuple[int, int], received_ns: int) -> None:
        with self.lock:
            self.latest = values
            self.samples.append(values)
            if len(self.pending) == self.pending.maxlen:
                self.dropped_samples += 1
            self.pending.append({"esp_timestamp_us": stamp,
                                 "pc_received_ns": received_ns,
                                 "fsr1_raw": values[0], "fsr2_raw": values[1]})
            self.last_sample = time.monotonic()
            self.connected = True

    @classmethod
    def parse_wifi_packet(cls, packet: bytes) -> tuple[int, int, tuple[int, int]] | None:
        try:
            parts = packet.decode("ascii").strip().split(",")
            if len(parts) != 5 or parts[0] != cls.WIFI_PACKET_PREFIX:
                return None
            sequence, stamp, raw1, raw2 = (int(part) for part in parts[1:])
        except (UnicodeDecodeError, ValueError):
            return None
        if not (0 <= sequence <= 0xFFFFFFFF and 0 <= stamp <= 0xFFFFFFFF
                and 0 <= raw1 <= 4095 and 0 <= raw2 <= 4095):
            return None
        return sequence, stamp, (raw1, raw2)

    def _read_wifi(self) -> None:
        while not self.stop_event.is_set():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
                    listener.bind(("0.0.0.0", self.wifi_port))
                    listener.settimeout(0.25)
                    while not self.stop_event.is_set():
                        try:
                            packet, address = listener.recvfrom(128)
                        except socket.timeout:
                            continue
                        received_ns = time.perf_counter_ns()
                        parsed = self.parse_wifi_packet(packet)
                        if parsed is None:
                            continue
                        sequence, stamp, values = parsed
                        with self.lock:
                            if self.source_ip != address[0] or time.monotonic() - self.last_sample > 2:
                                self.source_ip = address[0]
                                self.last_sequence = None
                            if self.last_sequence is not None:
                                delta = (sequence - self.last_sequence) & 0xFFFFFFFF
                                if delta == 0 or delta > 0x7FFFFFFF:
                                    continue
                                self.wifi_missed_packets += delta - 1
                            self.last_sequence = sequence
                        self._ingest(stamp, values, received_ns)
            except OSError:
                pass
            with self.lock:
                self.connected = False
            self.stop_event.wait(1.0)

    def _read_serial(self) -> None:
        while not self.stop_event.is_set():
            try:
                with serial.Serial(self.port, 115200, timeout=0.25) as device:
                    while not self.stop_event.is_set():
                        parts = device.readline().decode("ascii", errors="ignore").strip().split(",")
                        if len(parts) != 4 or parts[0] != "S":
                            continue
                        try:
                            stamp = int(parts[1])
                            values = int(parts[2]), int(parts[3])
                        except ValueError:
                            continue
                        if not 0 <= stamp <= 0xFFFFFFFF or not all(0 <= value <= 4095 for value in values):
                            continue
                        self._ingest(stamp, values, time.perf_counter_ns())
            except (serial.SerialException, OSError):
                pass
            with self.lock:
                self.connected = False
            self.stop_event.wait(1.0)

    def _calibrate_locked(self) -> None:
        if self.samples:
            self.baseline = tuple(statistics.median(row[index] for row in self.samples)
                                  for index in range(2))
            self.baseline_source = "manual_untouched"
            self.pressed = None

    def calibrate(self) -> bool:
        with self.lock:
            if len(self.samples) < 80:
                self.calibration_error = "Wait one second with both pads untouched"
                return False
            if all(a <= 20 and b <= 20 for a, b in list(self.samples)[-20:]):
                self.calibration_error = "Both channels near zero; check sensor power"
                return False
            recent = list(self.samples)[-80:]
            medians = [statistics.median(row[index] for row in recent) for index in range(2)]
            if medians[0] < 1000 or medians[1] < 2000:
                self.calibration_error = "Released values too low; release pads or check wiring"
                return False
            if any(max(row[index] for row in recent) - min(row[index] for row in recent) > 500
                   for index in range(2)):
                self.calibration_error = "Readings moved; hold pads and wiring still"
                return False
            self._calibrate_locked()
            self.calibration_error = "Press and hold both pads, then set pressed range"
            return True

    def calibrate_pressed(self) -> bool:
        with self.lock:
            if self.baseline is None or len(self.samples) < 50:
                self.calibration_error = "Set untouched baseline first"
                return False
            recent = list(self.samples)[-50:]
            pressed = tuple(statistics.median(row[index] for row in recent) for index in range(2))
            if any(self.baseline[index] - pressed[index] < 400 for index in range(2)):
                self.calibration_error = "Hold both pads firmly; each channel must fall at least 400 ADC counts"
                return False
            self.pressed = pressed
            self.calibration_error = ""
            return True

    def calibration_snapshot(self) -> dict:
        with self.lock:
            return {"status": "available" if self.baseline and self.pressed else "incomplete",
                    "source": self.baseline_source,
                    "baseline": list(self.baseline) if self.baseline else None,
                    "pressed": list(self.pressed) if self.pressed else None,
                    "direction": "decreasing",
                    "units": "relative pressure, not force"}

    def drain_samples(self) -> list[dict]:
        """Return every sensor packet received since the previous drain."""
        with self.lock:
            drained = list(self.pending)
            self.pending.clear()
            return drained

    def snapshot(self) -> dict:
        with self.lock:
            if self.latest is None:
                return {"status": "NO WIFI DATA" if self.transport == "wifi" else "NO SERIAL DATA",
                        "transport": self.transport, "port": self.port if self.transport == "serial" else None,
                        "wifi_port": self.wifi_port if self.transport == "wifi" else None,
                        "channels": []}
            fresh = self.connected and time.monotonic() - self.last_sample < 1.5
            # Both inputs near zero for a sustained interval also occurred when
            # the shared PCT power feed came loose. Treat it as ambiguous.
            signal_fault = len(self.samples) >= 20 and all(
                a <= 20 and b <= 20 for a, b in list(self.samples)[-20:])
            channels = []
            for index, raw in enumerate(self.latest):
                values = [row[index] for row in self.samples]
                span = max(values) - min(values)
                baseline = self.baseline[index] if self.baseline else None
                pressed = self.pressed[index] if self.pressed else None
                channels.append({"raw": raw, "baseline": baseline, "pressed": pressed, "range": span,
                                 "level": min(1.0, max(0.0, (baseline - raw) / (baseline - pressed)))
                                 if baseline is not None and pressed is not None and not signal_fault else 0.0,
                                 "unstable": signal_fault})
            return {"status": "CHECK SIGNAL" if signal_fault and fresh else "LIVE" if fresh else "STALE",
                    "transport": self.transport, "port": self.port if self.transport == "serial" else None,
                    "wifi_port": self.wifi_port if self.transport == "wifi" else None,
                    "source_ip": self.source_ip if self.transport == "wifi" else None,
                    "channels": channels, "calibrated": self.baseline is not None and self.pressed is not None,
                    "calibration_error": self.calibration_error,
                    "age_ms": round((time.monotonic() - self.last_sample) * 1000),
                    "dropped_samples": self.dropped_samples,
                    "wifi_missed_packets": self.wifi_missed_packets if self.transport == "wifi" else None}

    def close(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2)
