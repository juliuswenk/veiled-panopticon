#!/usr/bin/env python3

"""
Channel Impulse Response (CIR) test for spatial resolution.

The CSI frequency-domain response H(f) encodes all multipath reflections.
Taking the IFFT gives h(t) — the time-domain impulse response showing:
  - Direct path delay (distance sender→receiver)
  - Reflection path delays (sender→person→receiver)
  - Reflection strength (amplitude of each tap)

With 3 receivers, the differential delays between them encode position
along the receiver axis.

Expected resolution: ~10-20cm at 1m distance with 80MHz bandwidth.
"""

import ast
import cmath
import csv
import math
import signal
import sys
import time
from collections import deque

import numpy as np

RECEIVERS = {
    "left": "/dev/cu.usbmodem1101",
    "center": "/dev/cu.usbmodem101",
    "right": "/dev/cu.usbmodem2101",
}
BAUD = 921600
CAL_FRAMES = 200
EMIT_INTERVAL = 0.35
CIR_TAP_WINDOW = 32
CFO_CORRECTION = True


def parse_csi_complex(line):
    start = line.find("CSI_DATA")
    if start < 0:
        return None
    try:
        row = next(csv.reader([line[start:].strip()]))
        values = ast.literal_eval(row[-1])
        complex_vals = []
        amps = []
        for i in range(0, len(values) - 1, 2):
            imag = values[i]
            real = values[i + 1]
            complex_vals.append(complex(real, imag))
            amps.append(math.hypot(real, imag))
        if not complex_vals:
            return None
        return {"rssi": int(row[3]), "amps": amps, "complex": complex_vals}
    except Exception:
        return None


def estimate_cfo(complex_vals):
    """Estimate carrier frequency offset from phase slope across subcarriers."""
    n = len(complex_vals)
    if n < 4:
        return 0.0
    arr = np.array(complex_vals)
    prod = np.conjugate(arr[:-1]) * arr[1:]
    phase_diffs = np.angle(prod)
    return float(np.median(phase_diffs))


def correct_cfo(complex_vals, cfo_slope):
    """Remove linear phase trend (CFO) from CSI vector."""
    n = len(complex_vals)
    correction = np.exp(-1j * cfo_slope * np.arange(n))
    return np.array(complex_vals) * correction


def compute_cir(complex_vals, fft_size=256):
    """Compute Channel Impulse Response via zero-padded IFFT.

    Places CSI values at their correct subcarrier indices using the
    subcarrier mask, then IFFTs to get the multipath delay profile.
    """
    arr = np.array(complex_vals, dtype=complex)
    n = len(arr)

    # CSI values are ordered from lowest to highest subcarrier index.
    # For proper IFFT, DC should be at index 0.
    # Shift so that the center of the array moves to index 0.
    fft_input = np.zeros(fft_size, dtype=complex)
    half = n // 2
    fft_input[:half] = arr[half:]
    fft_input[fft_size - (n - half):] = arr[:half]

    cir = np.fft.ifft(fft_input)
    cir_mag = np.abs(np.fft.fftshift(cir))

    return cir_mag


def find_dominant_tap(cir, skip_first=2):
    if len(cir) <= skip_first:
        return 0, 0.0, 0.0
    search = cir[skip_first:]
    if not search:
        return 0, 0.0, 0.0
    max_idx = 0
    max_val = 0.0
    total_energy = 0.0
    for i, v in enumerate(search):
        total_energy += v * v
        if v > max_val:
            max_val = v
            max_idx = i
    energy_ratio = (max_val * max_val) / total_energy if total_energy > 0 else 0.0
    return max_idx + skip_first, max_val, energy_ratio


def cir_centroid(cir, skip_first=2):
    if len(cir) <= skip_first:
        return 0.0
    total_weight = 0.0
    weighted_sum = 0.0
    for i in range(skip_first, len(cir)):
        w = cir[i] * cir[i]
        total_weight += w
        weighted_sum += i * w
    if total_weight == 0:
        return 0.0
    return weighted_sum / total_weight


class CirTracker:
    """Track CIR metrics per receiver for spatial position estimation."""

    def __init__(self, fft_size=256):
        self.fft_size = fft_size
        self.cal_cir = {label: None for label in RECEIVERS}
        self.cal_dominant_tap = {label: 0 for label in RECEIVERS}
        self.cal_centroid = {label: 0.0 for label in RECEIVERS}
        self.cal_energy = {label: 0.0 for label in RECEIVERS}
        self.cal_frames = {label: [] for label in RECEIVERS}
        self.calibrated = False
        self.current_metrics = {}

    def update(self, label, complex_vals):
        n = len(complex_vals)

        # CFO correction
        if CFO_CORRECTION:
            cfo = estimate_cfo(complex_vals)
            complex_vals = correct_cfo(complex_vals, cfo)

        # Compute CIR
        cir = compute_cir(complex_vals, self.fft_size)

        # Find dominant tap (skip center region which is direct path)
        center = len(cir) // 2
        skip = max(4, self.fft_size // 32)
        search_left = cir[:center - skip]
        search_right = cir[center + skip:]

        # Combine both sides for dominant tap
        all_search = np.concatenate([search_left, search_right])
        if len(all_search) == 0:
            dom_idx = center
            dom_amp = 0.0
            energy_ratio = 0.0
        else:
            max_offset = int(np.argmax(all_search))
            if max_offset < len(search_left):
                dom_idx = max_offset
            else:
                dom_idx = center + skip + (max_offset - len(search_left))
            dom_amp = float(all_search[max_offset])

            total_energy = float(np.sum(cir ** 2))
            signal_energy = float(np.sum(all_search ** 2))
            energy_ratio = signal_energy / total_energy if total_energy > 0 else 0.0

        # Energy-weighted centroid (excluding center DC region)
        mask = np.ones(len(cir), dtype=bool)
        mask[center - skip:center + skip] = False
        if np.any(mask):
            energy = cir[mask] ** 2
            indices = np.where(mask)[0]
            total_weight = float(np.sum(energy))
            if total_weight > 0:
                centroid = float(np.sum(indices * energy) / total_weight)
            else:
                centroid = float(center)
        else:
            centroid = float(center)

        # Total CIR energy
        cir_mean = float(np.sqrt(np.mean(cir ** 2)))

        self.current_metrics[label] = {
            "cir": cir,
            "dominant_tap": dom_idx,
            "dominant_amp": dom_amp,
            "energy_ratio": energy_ratio,
            "centroid": centroid,
            "cir_mean": cir_mean,
            "center": center,
            "skip": skip,
        }

    def calibrate(self):
        """Capture calibration CIR from current frames."""
        for label in RECEIVERS:
            if label in self.current_metrics:
                m = self.current_metrics[label]
                self.cal_cir[label] = np.array(m["cir"])
                self.cal_dominant_tap[label] = m["dominant_tap"]
                self.cal_centroid[label] = m["centroid"]
                self.cal_energy[label] = m["cir_mean"]
        self.calibrated = True
        print(
            f"Calibrated CIR: "
            + "  ".join(
                f"{l}: tap={self.cal_dominant_tap[l]} cent={self.cal_centroid[l]:.1f}"
                for l in RECEIVERS
            ),
            flush=True,
        )

    def get_position_estimate(self):
        """Estimate position from differential CIR centroid shifts.

        When a person enters the room, they create new reflection paths
        that shift the CIR centroid. The differential shift between
        left/right receivers encodes lateral position.
        """
        if not self.calibrated:
            return 0.0, 0.0

        shifts = {}
        for label in RECEIVERS:
            if label not in self.current_metrics:
                return 0.0, 0.0
            m = self.current_metrics[label]
            cal_cent = self.cal_centroid.get(label, m["centroid"])
            shifts[label] = m["centroid"] - cal_cent

        left_shift = shifts.get("left", 0)
        center_shift = shifts.get("center", 0)
        right_shift = shifts.get("right", 0)

        total_shift = abs(left_shift) + abs(center_shift) + abs(right_shift)
        if total_shift < 0.1:
            return 0.0, 0.0

        # Y position from left-right differential
        y_raw = (left_shift - right_shift) / total_shift

        # Confidence from energy ratio + total shift magnitude
        energy_ratios = [
            self.current_metrics[l]["energy_ratio"]
            for l in RECEIVERS
            if l in self.current_metrics
        ]
        avg_energy_ratio = float(np.mean(energy_ratios)) if energy_ratios else 0.0
        confidence = min(1.0, avg_energy_ratio * 3) * min(1.0, total_shift / 5.0)

        return y_raw, confidence


def main():
    import serial

    streams = {}
    for label, port in RECEIVERS.items():
        streams[label] = serial.Serial(port, BAUD, timeout=0.005)
        print(f"[{label}] opened {port}", flush=True)

    tracker = CirTracker()
    cal_counts = {label: 0 for label in RECEIVERS}

    running = [True]

    def handle_signal(sig, frame):
        running[0] = False

    signal.signal(signal.SIGINT, handle_signal)

    started = time.monotonic()
    last_emit = 0.0

    print("Calibrating — stay still...", flush=True)

    try:
        while running[0]:
            for label, stream in streams.items():
                raw = stream.readline().decode("utf-8", "replace")
                parsed = parse_csi_complex(raw)
                if not parsed:
                    continue

                cal_counts[label] += 1
                tracker.update(label, parsed["complex"])

            if not tracker.calibrated and all(c >= CAL_FRAMES for c in cal_counts.values()):
                tracker.calibrate()
                continue

            if not tracker.calibrated:
                elapsed = time.monotonic() - started
                if elapsed - last_emit > 1.0:
                    last_emit = elapsed
                    print(
                        f"  calibrating left={cal_counts['left']}/{CAL_FRAMES} "
                        f"center={cal_counts['center']}/{CAL_FRAMES} "
                        f"right={cal_counts['right']}/{CAL_FRAMES}",
                        flush=True,
                    )
                continue

            now = time.monotonic()
            if now - last_emit < EMIT_INTERVAL:
                continue
            last_emit = now
            elapsed = now - started

            y_pos, confidence = tracker.get_position_estimate()

            print(f"\n--- {elapsed:.1f}s | y={y_pos:+.3f} conf={confidence:.3f} ---", flush=True)
            for label in RECEIVERS:
                m = tracker.current_metrics.get(label, {})
                cir = m.get("cir", np.array([]))
                center = m.get("center", len(cir) // 2)
                skip = m.get("skip", 8)

                # Show CIR taps around the dominant tap
                dom = m.get("dominant_tap", center)
                window = 6
                start = max(0, dom - window)
                end = min(len(cir), dom + window + 1)
                tap_vals = cir[start:end]
                tap_str = " ".join(f"{v:.2f}" for v in tap_vals)
                tap_label = f"...{' '.join(f'{i:>3d}' for i in range(start, end))}"

                print(
                    f"  {label:6s}: "
                    f"dom={dom:3d}  "
                    f"amp={m.get('dominant_amp', 0):.2f}  "
                    f"energy={m.get('energy_ratio', 0):.3f}  "
                    f"cent={m.get('centroid', 0):.1f}  "
                    f"rms={m.get('cir_mean', 0):.2f}\n"
                    f"         taps: {tap_str}\n"
                    f"         idx:  {tap_label}",
                    flush=True,
                )

    except Exception as e:
        print(f"\nerror: {e}", flush=True)
        import traceback
        traceback.print_exc()
    finally:
        for s in streams.values():
            s.close()
        print("\nstopping", flush=True)


if __name__ == "__main__":
    main()
