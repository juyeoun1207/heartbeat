#!/usr/bin/env python3
"""
Polar H10 Full Low-Latency BLE-to-UDP Bridge for Unity 6.3 (macOS Apple Silicon)
--------------------------------------------------------------------------------
Streams in real time via UDP (Port 5005) to Unity:
  1. Heart Rate (BPM) & Exact RR-Intervals (ms, 1/1024s resolution) via GATT 0x2A37
  2. Live Heart Rate Variability (HRV) metrics: RMSSD (ms), SDNN (ms), pNN50 (%)
  3. 130 Hz Raw ECG Waveform (microvolts, uV) + Real-Time QRS / R-Peak Detection
     via Polar Measurement Data (PMD) Service (FB005C80-02E7-F387-1CAD-8ACD2D8DF0C8)
  4. Sensor Skin Contact Status & Battery Level (%)

Designed for minimal latency so Unity's 'Real' biofeedback mode is phase-locked
to the participant's actual cardiac R-peaks.
"""

import argparse
import asyncio
import collections
import json
import math
import random
import socket
import statistics
import sys
import time
from typing import Deque, List, Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

# Standard Bluetooth SIG UUIDs
HR_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HR_MEASUREMENT_CHAR_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL_CHAR_UUID = "00002a19-0000-1000-8000-00805f9b34fb"

# Polar H10 Proprietary PMD (Polar Measurement Data) UUIDs for 130 Hz Raw ECG
PMD_SERVICE_UUID = "fb005c80-02e7-f387-1cad-8acd2d8df0c8"
PMD_CONTROL_UUID = "fb005c81-02e7-f387-1cad-8acd2d8df0c8"
PMD_DATA_UUID = "fb005c82-02e7-f387-1cad-8acd2d8df0c8"

# Command to start 130 Hz, 14-bit Raw ECG stream on Polar H10
ECG_WRITE_START = bytearray([0x02, 0x00, 0x00, 0x01, 0x82, 0x00, 0x01, 0x01, 0x0E, 0x00])


class HRVCalculator:
    """Computes rolling time-domain HRV metrics (RMSSD, SDNN, pNN50) from RR-intervals."""

    def __init__(self, window_size: int = 60):
        self.rr_history: Deque[float] = collections.deque(maxlen=window_size)

    def add_rr_intervals(self, rr_list_ms: List[float]) -> None:
        for rr in rr_list_ms:
            # Filter physiologically plausible NN intervals (300ms = 200 BPM, 2000ms = 30 BPM)
            if 300.0 <= rr <= 2000.0:
                self.rr_history.append(rr)

    def compute_metrics(self) -> dict:
        n = len(self.rr_history)
        if n < 2:
            return {"rmssd_ms": 0.0, "sdnn_ms": 0.0, "pnn50_pct": 0.0}

        rr_list = list(self.rr_history)
        diffs = [rr_list[i + 1] - rr_list[i] for i in range(n - 1)]
        sq_diffs = [d * d for d in diffs]

        rmssd = math.sqrt(sum(sq_diffs) / len(sq_diffs))
        sdnn = statistics.stdev(rr_list) if n >= 2 else 0.0
        nn50 = sum(1 for d in diffs if abs(d) > 50.0)
        pnn50 = (nn50 / len(diffs)) * 100.0

        return {
            "rmssd_ms": round(rmssd, 2),
            "sdnn_ms": round(sdnn, 2),
            "pnn50_pct": round(pnn50, 1),
        }


class RealTimeRPeakDetector:
    """
    Fast, zero-phase-delay R-peak detector for 130 Hz Polar H10 ECG (in microvolts).
    Tracks adaptive QRS peak envelope with a 280 ms physiological refractory period.
    """

    def __init__(self, sample_rate: int = 130):
        self.sample_rate = sample_rate
        self.refractory_samples = int(0.28 * sample_rate)  # ~36 samples (280 ms)
        self.samples_since_last_peak = self.refractory_samples
        self.running_threshold = 450.0  # Initial threshold in uV
        self.prev_sample = 0.0

    def process_ecg_frame(self, samples_uv: List[int]) -> bool:
        r_peak_detected = False
        for s in samples_uv:
            self.samples_since_last_peak += 1
            val = float(s)
            slope = abs(val - self.prev_sample)
            self.prev_sample = val

            # Slowly decay threshold toward baseline so it adapts to skin impedance
            self.running_threshold = max(250.0, self.running_threshold * 0.9985)

            # Detect sharp R-peak upstroke exceeding adaptive threshold outside refractory window
            if (
                self.samples_since_last_peak >= self.refractory_samples
                and val > self.running_threshold
                and slope > 120.0
            ):
                r_peak_detected = True
                self.samples_since_last_peak = 0
                self.running_threshold = min(2500.0, max(self.running_threshold, val * 0.68))

        return r_peak_detected


def parse_heart_rate_measurement(data: bytearray) -> dict:
    """Decodes BLE GATT Heart Rate Measurement (0x2A37)."""
    flags = data[0]
    is_uint16_hr = (flags & 0x01) != 0
    sensor_contact_supported = (flags & 0x04) != 0
    sensor_contact_detected = (flags & 0x02) != 0 if sensor_contact_supported else True
    has_energy_expended = (flags & 0x08) != 0
    has_rr_intervals = (flags & 0x10) != 0

    offset = 1
    if is_uint16_hr:
        bpm = int.from_bytes(data[offset : offset + 2], byteorder="little")
        offset += 2
    else:
        bpm = data[offset]
        offset += 1

    if has_energy_expended:
        offset += 2

    rr_intervals_ms: List[float] = []
    if has_rr_intervals:
        while offset + 1 < len(data):
            raw_rr = int.from_bytes(data[offset : offset + 2], byteorder="little")
            rr_ms = round((raw_rr / 1024.0) * 1000.0, 2)
            rr_intervals_ms.append(rr_ms)
            offset += 2

    return {
        "bpm": bpm,
        "rr_ms": rr_intervals_ms,
        "contact": sensor_contact_detected,
    }


def parse_pmd_ecg_packet(data: bytearray) -> List[int]:
    """
    Decodes Polar H10 PMD ECG frame (0x00).
    Byte 0: Measurement type (0x00 = ECG)
    Bytes 1..8: 64-bit sensor timestamp (ns)
    Byte 9: Frame type (0x00 = raw 24-bit signed microvolts)
    Bytes 10..N: 3-byte signed little-endian integers (uV)
    """
    if len(data) < 10 or data[0] != 0x00:
        return []

    samples_uv: List[int] = []
    offset = 10
    while offset + 2 < len(data):
        uv = int.from_bytes(data[offset : offset + 3], byteorder="little", signed=True)
        samples_uv.append(uv)
        offset += 3
    return samples_uv


class PolarUDPBridge:
    def __init__(self, target_ip: str, target_port: int, device_name_filter: str = "Polar H10"):
        self.target_ip = target_ip
        self.target_port = target_port
        self.device_name_filter = device_name_filter
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.hrv = HRVCalculator(window_size=60)
        self.rpeak_detector = RealTimeRPeakDetector(sample_rate=130)

        # Shared telemetry state
        self.packet_count = 0
        self.battery_pct = -1
        self.latest_bpm = 0
        self.latest_rr_ms = 0.0
        self.latest_contact = True
        self.ecg_active = False

    def send_udp(
        self,
        packet_type: str,
        rr_ms: List[float],
        ecg_uv: List[int],
        r_peak: bool,
        simulated: bool = False,
    ) -> None:
        self.packet_count += 1
        hrv_metrics = self.hrv.compute_metrics()

        payload = {
            "seq": self.packet_count,
            "packet_type": packet_type,  # "hr" or "ecg"
            "timestamp": round(time.time(), 4),
            "bpm": self.latest_bpm,
            "rr_ms": rr_ms,
            "latest_rr_ms": self.latest_rr_ms,
            "rmssd_ms": hrv_metrics["rmssd_ms"],
            "sdnn_ms": hrv_metrics["sdnn_ms"],
            "pnn50_pct": hrv_metrics["pnn50_pct"],
            "battery_pct": self.battery_pct,
            "contact": self.latest_contact,
            "ecg_active": self.ecg_active,
            "r_peak": r_peak,
            "ecg_uv": ecg_uv,
            "simulated": simulated,
        }

        msg = json.dumps(payload).encode("utf-8")
        self.sock.sendto(msg, (self.target_ip, self.target_port))

        if packet_type == "hr":
            rr_str = ", ".join(f"{r:.1f}ms" for r in rr_ms) if rr_ms else f"{self.latest_rr_ms:.1f}ms"
            mode_tag = "[SIM]" if simulated else "[H10]"
            ecg_tag = "ECG:130Hz" if self.ecg_active else "ECG:WAIT"
            print(
                f"{mode_tag} #{self.packet_count:04d} | "
                f"HR: {self.latest_bpm:3d} BPM | "
                f"RR: [{rr_str}] | "
                f"RMSSD: {hrv_metrics['rmssd_ms']:5.1f}ms | "
                f"SDNN: {hrv_metrics['sdnn_ms']:5.1f}ms | "
                f"Batt: {self.battery_pct}% | {ecg_tag}"
            )

    async def scan_for_polar(self, timeout: float = 6.0) -> Optional[BLEDevice]:
        print(f"🔍 Suche nach '{self.device_name_filter}' via Bluetooth Low Energy ({timeout}s)...")
        devices = await BleakScanner.discover(timeout=timeout)

        for d in devices:
            if d.name and self.device_name_filter.lower() in d.name.lower():
                print(f"✅ Gefunden: {d.name} (UUID/Address: {d.address})")
                return d

        print("\n⚠️  Kein Polar H10 gefunden. Bitte sicherstellen, dass der Gurt angelegt ist.")
        return None

    async def run_ble(self) -> None:
        while True:
            device = await self.scan_for_polar()
            if not device:
                print("🔄 Neuer Scan in 3 Sekunden... (Drücke Ctrl+C zum Beenden)")
                await asyncio.sleep(3.0)
                continue

            print(f"🔗 Verbinde mit {device.name} ({device.address})...")
            disconnected_event = asyncio.Event()

            def on_disconnect(_client: BleakClient):
                print("\n❌ Verbindung zum Polar H10 getrennt!")
                self.ecg_active = False
                disconnected_event.set()

            def hr_notification_handler(_sender, data: bytearray):
                parsed = parse_heart_rate_measurement(data)
                self.latest_bpm = parsed["bpm"]
                self.latest_contact = parsed["contact"]
                rr_list = parsed["rr_ms"]
                has_new_beat = len(rr_list) > 0

                if has_new_beat:
                    self.latest_rr_ms = rr_list[-1]
                    self.hrv.add_rr_intervals(rr_list)
                elif self.latest_bpm > 0 and self.latest_rr_ms == 0.0:
                    self.latest_rr_ms = round(60000.0 / self.latest_bpm, 2)

                # If PMD ECG isn't active yet, use GATT RR notification as beat trigger
                r_peak_trigger = has_new_beat and (not self.ecg_active)
                self.send_udp(
                    packet_type="hr",
                    rr_ms=rr_list,
                    ecg_uv=[],
                    r_peak=r_peak_trigger,
                    simulated=False,
                )

            def pmd_control_handler(_sender, data: bytearray):
                # Control point response from Polar H10
                pass

            def pmd_data_handler(_sender, data: bytearray):
                ecg_samples = parse_pmd_ecg_packet(data)
                if not ecg_samples:
                    return
                self.ecg_active = True
                r_peak_now = self.rpeak_detector.process_ecg_frame(ecg_samples)
                self.send_udp(
                    packet_type="ecg",
                    rr_ms=[],
                    ecg_uv=ecg_samples,
                    r_peak=r_peak_now,
                    simulated=False,
                )

            try:
                async with BleakClient(device, disconnected_callback=on_disconnect) as client:
                    print(f"🎉 Verbunden mit {device.name}!")

                    # 1. Read Battery Level
                    try:
                        batt = await client.read_gatt_char(BATTERY_LEVEL_CHAR_UUID)
                        self.battery_pct = int(batt[0])
                        print(f"🔋 Batteriestand Polar H10: {self.battery_pct}%")
                    except Exception:
                        self.battery_pct = -1

                    # 2. Start Standard GATT Heart Rate & RR-Interval Stream (0x2A37)
                    await client.start_notify(HR_MEASUREMENT_CHAR_UUID, hr_notification_handler)
                    print("💓 GATT Heart Rate & RR-Interval Stream (0x2A37) aktiv.")

                    # 3. Start Polar PMD 130 Hz Raw ECG Stream
                    try:
                        await client.start_notify(PMD_CONTROL_UUID, pmd_control_handler)
                        await client.start_notify(PMD_DATA_UUID, pmd_data_handler)
                        await client.write_gatt_char(PMD_CONTROL_UUID, ECG_WRITE_START, response=True)
                        print("📈 Polar PMD 130 Hz Roh-EKG Stream (uV) erfolgreich aktiviert!")
                    except Exception as pmd_err:
                        print(f"⚠️  Hinweis: PMD 130 Hz EKG konnte nicht gestartet werden ({pmd_err}). Nutze GATT RR-Stream.")

                    print(f"📡 Sende Echtzeit-Daten an Unity ({self.target_ip}:{self.target_port})...\n")
                    await disconnected_event.wait()
            except Exception as e:
                print(f"⚠️  Verbindungsfehler: {e}")
                await asyncio.sleep(2.0)

    async def run_simulation(self, base_bpm: float = 70.0) -> None:
        print(f"🧪 Starte Polar H10 VOLL-SIMULATION (BPM + RR + HRV + 130 Hz EKG)")
        print(f"📡 Sende UDP-Pakete an Unity ({self.target_ip}:{self.target_port})...\n")
        self.battery_pct = 92
        self.ecg_active = True
        start_time = time.time()
        last_hr_send = 0.0
        phase = 0.0

        while True:
            now = time.time()
            elapsed = now - start_time
            current_bpm = int(round(base_bpm + 4.0 * math.sin(elapsed * 0.22)))
            rr_ms = round(60000.0 / current_bpm + random.uniform(-15.0, 15.0), 2)
            self.latest_bpm = current_bpm
            self.latest_rr_ms = rr_ms

            # Generate 13 samples of 130 Hz ECG every 100 ms
            ecg_chunk: List[int] = []
            r_peak_in_chunk = False
            freq_hz = current_bpm / 60.0
            dt = 1.0 / 130.0

            for _ in range(13):
                prev_phase = phase
                phase = (phase + freq_hz * dt) % 1.0
                if phase < prev_phase:
                    r_peak_in_chunk = True

                # Synthesize realistic P-Q-R-S-T morphology in microvolts
                p_wave = 120.0 * math.exp(-((phase - 0.82) ** 2) / (2 * 0.025**2))
                q_wave = -180.0 * math.exp(-((phase - 0.97) ** 2) / (2 * 0.008**2))
                r_wave = 1450.0 * math.exp(-((phase - 0.0) ** 2) / (2 * 0.010**2)) + 1450.0 * math.exp(
                    -((phase - 1.0) ** 2) / (2 * 0.010**2)
                )
                s_wave = -320.0 * math.exp(-((phase - 0.03) ** 2) / (2 * 0.009**2))
                t_wave = 260.0 * math.exp(-((phase - 0.28) ** 2) / (2 * 0.040**2))
                noise = random.uniform(-18.0, 18.0)

                uv = int(round(p_wave + q_wave + r_wave + s_wave + t_wave + noise))
                ecg_chunk.append(uv)

            self.send_udp(packet_type="ecg", rr_ms=[], ecg_uv=ecg_chunk, r_peak=r_peak_in_chunk, simulated=True)

            if now - last_hr_send >= 1.0:
                last_hr_send = now
                self.hrv.add_rr_intervals([rr_ms])
                self.send_udp(packet_type="hr", rr_ms=[rr_ms], ecg_uv=[], r_peak=False, simulated=True)

            await asyncio.sleep(0.10)


def main():
    parser = argparse.ArgumentParser(description="Polar H10 Low-Latency BLE to Unity UDP Bridge")
    parser.add_argument("--ip", type=str, default="127.0.0.1", help="Target IP (127.0.0.1 for Mac Editor, or Quest 3S IP)")
    parser.add_argument("--port", type=int, default=5005, help="Target UDP Port (default: 5005)")
    parser.add_argument("--name", type=str, default="Polar H10", help="BLE device name filter (default: 'Polar H10')")
    parser.add_argument("--simulate", action="store_true", help="Simulate Polar H10 (HR + HRV + 130Hz ECG)")
    args = parser.parse_args()

    bridge = PolarUDPBridge(target_ip=args.ip, target_port=args.port, device_name_filter=args.name)

    try:
        if args.simulate:
            asyncio.run(bridge.run_simulation())
        else:
            asyncio.run(bridge.run_ble())
    except KeyboardInterrupt:
        print("\n👋 Bridge beendet.")
        sys.exit(0)


if __name__ == "__main__":
    main()
