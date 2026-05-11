#!/usr/bin/env python3

"""
Phase-based Y position tracking via inter-receiver cross-correlation.

The sender's clock/phase noise affects all receivers equally. By computing
the complex cross-correlation between adjacent receiver pairs (left-center
and center-right), the common-mode noise cancels and the remaining phase
shift encodes the spatial position of reflections.

Phase-difference between pairs maps to Y position:
  - dphi_LC ≈ dphi_CR → person centered (Y ≈ 0)
  - dphi_LC > dphi_CR → person toward left (Y < 0)
  - dphi_LC < dphi_CR → person toward right (Y > 0)
"""

import ast
import cmath
import csv
import math
import signal
import sys
import time
from collections import deque

RECEIVERS = {
    "left": "/dev/cu.usbmodem1101",
    "center": "/dev/cu.usbmodem101",
    "right": "/dev/cu.usbmodem2101",
}
BAUD = 921600
CAL_FRAMES = 200
EMIT_INTERVAL = 0.35
PHASE_SMOOTH_ALPHA = 0.15


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


def wrap_pi(v):
    while v <= -math.pi:
        v += math.tau
    while v > math.pi:
        v -= math.tau
    return v


def complex_correlation(a, b, weight_by_amp=True):
    """Complex cross-correlation between two CSI vectors.
    
    Returns (phase_diff, magnitude) where phase_diff is the average
    phase shift from a to b, and magnitude indicates correlation strength.
    """
    w = min(len(a), len(b))
    if w < 10:
        return 0.0, 0.0
    
    if weight_by_amp:
        # Weight by product of amplitudes — strong subcarriers dominate
        weighted_sum = complex(0, 0)
        weight_total = 0.0
        for i in range(w):
            amp_a = abs(a[i])
            amp_b = abs(b[i])
            weight = amp_a * amp_b
            weighted_sum += a[i].conjugate() * b[i]
            weight_total += weight
        if weight_total < 1e-6:
            return 0.0, 0.0
        result = weighted_sum / weight_total
    else:
        total = complex(0, 0)
        for i in range(w):
            total += a[i].conjugate() * b[i]
        result = total / w
    
    return cmath.phase(result), abs(result)


class PhasePositionTracker:
    """Tracks Y position via inter-receiver phase differences.
    
    Uses complex cross-correlation between receiver pairs to extract
    the spatial phase shift, which encodes position along the receiver axis.
    """
    
    def __init__(self, alpha=PHASE_SMOOTH_ALPHA):
        self.alpha = alpha
        self.smoothed_dphi_lc = 0.0
        self.smoothed_dphi_cr = 0.0
        self.smoothed_y = 0.0
        self.smoothed_strength = 0.0
        self.phase_history_lc = deque(maxlen=20)
        self.phase_history_cr = deque(maxlen=20)
        self.cal_phase_lc = None
        self.cal_phase_cr = None
        self.cal_frames = []
        self.calibrated = False
    
    def add_calibration_frame(self, dphi_lc, dphi_cr):
        self.cal_phase_lc = dphi_lc
        self.cal_phase_cr = dphi_cr
        self.calibrated = True
    
    def update(self, dphi_lc, dphi_cr, strength):
        if self.calibrated:
            # Subtract calibration baseline
            dphi_lc = wrap_pi(dphi_lc - self.cal_phase_lc)
            dphi_cr = wrap_pi(dphi_cr - self.cal_phase_cr)
        
        self.phase_history_lc.append(dphi_lc)
        self.phase_history_cr.append(dphi_cr)
        
        self.smoothed_dphi_lc = (
            (1 - self.alpha) * self.smoothed_dphi_lc + self.alpha * dphi_lc
        )
        self.smoothed_dphi_cr = (
            (1 - self.alpha) * self.smoothed_dphi_cr + self.alpha * dphi_cr
        )
        self.smoothed_strength = (
            0.9 * self.smoothed_strength + 0.1 * strength
        )
        
        # Y position: differential between the two phase differences
        y_raw = self.smoothed_dphi_lc - self.smoothed_dphi_cr
        y_raw = wrap_pi(y_raw)
        self.smoothed_y = (
            0.85 * self.smoothed_y + 0.15 * y_raw
        )
        
        return {
            "dphi_lc": self.smoothed_dphi_lc,
            "dphi_cr": self.smoothed_dphi_cr,
            "y_raw": y_raw,
            "y_smooth": self.smoothed_y,
            "strength": self.smoothed_strength,
            "dphi_lc_std": _std(self.phase_history_lc),
            "dphi_cr_std": _std(self.phase_history_cr),
        }


def _std(values):
    if len(values) < 2:
        return 0.0
    m = sum(values) / len(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / len(values))


def main():
    import serial
    
    streams = {}
    for label, port in RECEIVERS.items():
        streams[label] = serial.Serial(port, BAUD, timeout=0.005)
        print(f"[{label}] opened {port}", flush=True)
    
    tracker = PhasePositionTracker()
    
    running = [True]
    def handle_signal(sig, frame):
        running[0] = False
    signal.signal(signal.SIGINT, handle_signal)
    
    started = time.monotonic()
    last_emit = 0.0
    cal_counts = {"left": 0, "center": 0, "right": 0}
    cal_done = False
    last_complex = {}
    
    print("Calibrating — stay still...", flush=True)
    
    try:
        while running[0]:
            frame_data = {}
            for label, stream in streams.items():
                raw = stream.readline().decode("utf-8", "replace")
                parsed = parse_csi_complex(raw)
                if parsed:
                    frame_data[label] = parsed
                    cal_counts[label] += 1
            
            if not cal_done and all(c >= CAL_FRAMES for c in cal_counts.values()):
                # Calibration complete — use last good frames
                if all(k in frame_data for k in RECEIVERS):
                    lc_phase, _ = complex_correlation(
                        frame_data["left"]["complex"],
                        frame_data["center"]["complex"]
                    )
                    cr_phase, _ = complex_correlation(
                        frame_data["center"]["complex"],
                        frame_data["right"]["complex"]
                    )
                    tracker.add_calibration_frame(lc_phase, cr_phase)
                    cal_done = True
                    print(
                        f"Calibrated: dphi_lc={lc_phase:.3f} dphi_cr={cr_phase:.3f}",
                        flush=True,
                    )
                continue
            
            if not cal_done:
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
            
            if not all(k in frame_data for k in RECEIVERS):
                continue
            
            left_c = frame_data["left"]["complex"]
            center_c = frame_data["center"]["complex"]
            right_c = frame_data["right"]["complex"]
            
            dphi_lc, mag_lc = complex_correlation(left_c, center_c)
            dphi_cr, mag_cr = complex_correlation(center_c, right_c)
            
            avg_mag = (mag_lc + mag_cr) / 2
            
            result = tracker.update(dphi_lc, dphi_cr, avg_mag)
            
            now = time.monotonic()
            if now - last_emit < EMIT_INTERVAL:
                continue
            last_emit = now
            elapsed = now - started
            
            print(
                f"\n--- {elapsed:.1f}s | strength={result['strength']:.3f} ---",
                flush=True,
            )
            print(
                f"  dphi_lc={result['dphi_lc']:+.4f} (σ={result['dphi_lc_std']:.4f})  "
                f"dphi_cr={result['dphi_cr']:+.4f} (σ={result['dphi_cr_std']:.4f})",
                flush=True,
            )
            print(
                f"  y_raw={result['y_raw']:+.4f}  "
                f"y_smooth={result['y_smooth']:+.4f}",
                flush=True,
            )
            print(
                f"  amps: left={sum(frame_data['left']['amps'])/len(frame_data['left']['amps']):.1f}  "
                f"center={sum(frame_data['center']['amps'])/len(frame_data['center']['amps']):.1f}  "
                f"right={sum(frame_data['right']['amps'])/len(frame_data['right']['amps']):.1f}",
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
