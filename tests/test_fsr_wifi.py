import socket
import time
import unittest

from app.fsr_reader import FSRReader


class FSRWiFiTests(unittest.TestCase):
    def test_packet_validation(self):
        self.assertEqual(FSRReader.parse_wifi_packet(b"VECTOR_FSR_V1,7,12345,3200,4095"),
                         (7, 12345, (3200, 4095)))
        for packet in (b"VECTOR_FSR_V1,7,12345,3200,4096",
                       b"VECTOR_FSR_V1,7,12345,3200",
                       b"wrong,7,12345,3200,4095",
                       b"\xff"):
            self.assertIsNone(FSRReader.parse_wifi_packet(packet))

    def test_udp_samples_reach_live_snapshot_and_recorder_queue(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        reader = FSRReader(transport="wifi", wifi_port=port)
        reader.start()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                deadline = time.monotonic() + 2
                while reader.snapshot()["status"] != "LIVE" and time.monotonic() < deadline:
                    sender.sendto(b"VECTOR_FSR_V1,1,10000,3000,4000", ("127.0.0.1", port))
                    time.sleep(0.02)
                self.assertEqual(reader.snapshot()["status"], "LIVE")
                sender.sendto(b"VECTOR_FSR_V1,3,30000,2500,3500", ("127.0.0.1", port))
                deadline = time.monotonic() + 1
                while reader.snapshot()["channels"][0]["raw"] != 2500 and time.monotonic() < deadline:
                    time.sleep(0.01)
            snapshot = reader.snapshot()
            self.assertEqual(snapshot["transport"], "wifi")
            self.assertEqual([channel["raw"] for channel in snapshot["channels"]], [2500, 3500])
            self.assertEqual(snapshot["wifi_missed_packets"], 1)
            self.assertEqual(reader.drain_samples()[-1]["esp_timestamp_us"], 30000)
        finally:
            reader.close()


if __name__ == "__main__":
    unittest.main()
