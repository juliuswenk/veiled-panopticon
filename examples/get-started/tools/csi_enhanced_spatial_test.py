#!/usr/bin/env python3

"""
Enhanced spatial position detection via:
  1. Per-subcarrier sensitivity weighting (CoV-based)
  2. Cross-receiver amplitude correlation patterns

Subcarrier weighting:
  During calibration, each subcarrier's amplitude variability (CoV = std/mean)
  is measured. Subcarriers that fluctuate more are more sensitive to environment
  changes and get higher weight. This amplifies the signal from motion-sensitive
  frequencies while suppressing static ones.

Cross-receiver correlation:
  Amplitude patterns between adjacent receivers are correlated. When a person
  enters near one receiver, that receiver's pattern diverges from neighbors.
  The differential correlation drop encodes lateral position:
    - corr(L,C) drops more than corr(C,R) → person toward left
    - corr(C,R) drops more than corr(L,C) → person toward right
    - Both drop equally → person centered
"""

import ast
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
ZONE_ORDER = ("left", "center", "right")

BAUD = 921600
CAL_FRAMES = 200
EMIT_INTERVAL = 0.35
ROLLING_WINDOW = 150
TOP_PCT = 0.20


def parse_csi_line(line):
    start = line.find("CSI_DATA")
    if start < 0:
        return None
    try:
        row = next(csv.reader([line[start:].strip()]))
        values = ast.literal_eval(row[-1])
        amps = []
        for i in range(0, len(values) - 1, 2):
            imag = values[i]
            real = values[i + 1]
            amps.append(math.hypot(real, imag))
        if not amps:
            return None
        return {"rssi": int(row[3]), "amps": amps}
    except Exception:
        return None


def pearson_correlation(a, b):
    n = min(len(a), len(b))
    if n < 10:
        return 0.0
    a = a[:n]
    b = b[:n]
    a_mean = np.mean(a)
    b_mean = np.mean(b)
    a_std = np.std(a)
    b_std = np.std(b)
    if a_std < 1e-6 or b_std < 1e-6:
        return 0.0
    return float(np.mean((a - a_mean) * (b - b_mean)) / (a_std * b_std))


def top_percentile_mean(values, pct):
    if not values:
        return 0.0
    top_k = max(1, int(len(values) * pct))
    top_vals = sorted(values)[-top_k:]
    return sum(top_vals) / top_k


def median_vector(frames):
    if not frames:
        return np.array([])
    arr = np.array(frames)
    return np.median(arr, axis=0)


class EnhancedSpatialTracker:
    """Combines subcarrier-weighted amplitude with cross-receiver correlation."""

    def __init__(self):
        self.cal_amps = {label: [] for label in ZONE_ORDER}
        self.calibrated = False

        # Per-subcarrier sensitivity weights
        self.subcarrier_weights = {label: None for label in ZONE_ORDER}
        self.combined_weights = None

        # Calibration baselines
        self.baseline = {label: None for label in ZONE_ORDER}
        self.cal_weighted_deltas = {label: [] for label in ZONE_ORDER}

        # Per-receiver runtime state
        self.rolling_window = {label: deque(maxlen=ROLLING_WINDOW) for label in ZONE_ORDER}
        self.prev_amps = {label: None for label in ZONE_ORDER}

        # Per-receiver metrics
        self.top_pct_presence = {label: 0.0 for label in ZONE_ORDER}
        self.motion_presence = {label: 0.0 for label in ZONE_ORDER}
        self.combined_presence = {label: 0.0 for label in ZONE_ORDER}
        self.weighted_score = {label: 0.0 for label in ZONE_ORDER}
        self.weighted_top_pct = {label: 0.0 for label in ZONE_ORDER}
        self.motion_raw = {label: 0.0 for label in ZONE_ORDER}

        # Cross-receiver correlation
        self.cal_corr_lc = 0.0
        self.cal_corr_cr = 0.0
        self.corr_lc = 0.0
        self.corr_cr = 0.0
        self.corr_differential = 0.0
        self.corr_smoothed = 0.0

        # Final position estimate
        self.y_position = 0.0
        self.spatial_confidence = 0.0

        # Calibration baseline stats for normalization
        self.cal_top_pct_mean = 0.0
        self.cal_top_pct_std = 0.0
        self.cal_motion_mean = 0.0
        self.cal_motion_std = 0.0

    def add_calibration_frame(self, label, amps):
        self.cal_amps[label].append(np.array(amps))

    def compute_calibration(self):
        all_rolling_deltas = []

        for label in ZONE_ORDER:
            frames = self.cal_amps[label]
            if len(frames) < 10:
                return False

            arr = np.array(frames)
            means = np.mean(arr, axis=0)
            stds = np.std(arr, axis=0)

            min_mean = max(0.1, np.percentile(means, 10))
            cov = stds / np.maximum(means, min_mean)

            weight_sum = np.sum(cov)
            if weight_sum > 0:
                self.subcarrier_weights[label] = cov / weight_sum
            else:
                self.subcarrier_weights[label] = np.ones(len(cov)) / len(cov)

            self.baseline[label] = means.copy()

            # Compute calibration weighted deltas for normalization baseline
            for i in range(1, len(frames)):
                delta = np.abs(frames[i] - frames[i - 1])
                w_delta = delta * self.subcarrier_weights[label][:len(delta)]
                w_sum = float(np.sum(w_delta))
                self.cal_weighted_deltas[label].append(w_sum)

        # Combined weight = geometric mean across receivers
        all_weights = np.stack([self.subcarrier_weights[l] for l in ZONE_ORDER])
        log_weights = np.log(np.maximum(all_weights, 1e-10))
        self.combined_weights = np.exp(np.mean(log_weights, axis=0))
        self.combined_weights /= np.sum(self.combined_weights)

        # Calibration correlation from last frames
        last_frames = {l: self.cal_amps[l][-1] for l in ZONE_ORDER}
        self.cal_corr_lc = pearson_correlation(last_frames["left"], last_frames["center"])
        self.cal_corr_cr = pearson_correlation(last_frames["center"], last_frames["right"])

        # Compute rolling-window calibration stats for normalization
        motion_values = []
        for label in ZONE_ORDER:
            frames = self.cal_amps[label]
            weights = self.subcarrier_weights[label]
            for i in range(30, len(frames)):
                window = frames[i - 30:i]
                bl = np.median(window, axis=0)
                delta = np.abs(frames[i] - bl)
                w_delta = delta * weights[:len(delta)]
                top_k = max(1, int(len(w_delta) * TOP_PCT))
                top_vals = np.sort(w_delta)[-top_k:]
                all_rolling_deltas.append(float(np.mean(top_vals)))

                if i > 30:
                    motion = float(np.mean(np.abs(frames[i] - frames[i - 1])))
                    motion_values.append(motion)

        n_cal = len(all_rolling_deltas)
        if n_cal > 0:
            self.cal_top_pct_mean = np.mean(all_rolling_deltas)
            self.cal_top_pct_std = np.std(all_rolling_deltas)
        if motion_values:
            self.cal_motion_mean = float(np.mean(motion_values))
            self.cal_motion_std = max(0.01, float(np.std(motion_values)))

        self.calibrated = True

        weight_info = ""
        for label in ZONE_ORDER:
            w = self.subcarrier_weights[label]
            top5 = np.sort(w)[-5:]
            weight_info += f" {label}:w=[{top5[0]:.4f}..{top5[-1]:.4f}]"

        print(
            f"Calibrated: top_pct μ={self.cal_top_pct_mean:.3f} σ={self.cal_top_pct_std:.3f}  "
            f"motion μ={self.cal_motion_mean:.3f} σ={self.cal_motion_std:.3f}  "
            f"corr LC={self.cal_corr_lc:.3f} CR={self.cal_corr_cr:.3f}"
            f"{weight_info}",
            flush=True,
        )
        return True

    def update(self, label, amps):
        if not self.calibrated:
            return

        amps_arr = np.array(amps)
        baseline = self.baseline[label]
        if baseline is None:
            return

        weights = self.subcarrier_weights[label]
        if weights is None:
            return

        width = min(len(amps_arr), len(baseline))

        # Rolling window
        self.rolling_window[label].append(amps_arr)
        if len(self.rolling_window[label]) >= 30:
            rolling_bl = median_vector(list(self.rolling_window[label]))
            rolling_delta = np.abs(amps_arr[:width] - rolling_bl[:width])

            # Weighted top-percentile
            w_delta = rolling_delta * weights[:width]
            top_k = max(1, int(width * TOP_PCT))
            top_vals = np.sort(w_delta)[-top_k:]
            top_pct_val = float(np.mean(top_vals))

            # Normalize by calibration stats (z-score, clamped to 0-1)
            if self.cal_top_pct_std > 0:
                top_pct_norm = max(0.0, (top_pct_val - self.cal_top_pct_mean) / self.cal_top_pct_std)
            else:
                top_pct_norm = 0.0
            top_pct_norm = min(top_pct_norm, 1.0)

            # Motion
            prev = self.prev_amps[label]
            if prev is not None:
                motion_raw = float(np.mean(np.abs(amps_arr - prev)))
            else:
                motion_raw = 0.0
            self.prev_amps[label] = amps_arr.copy()
            self.motion_raw[label] = motion_raw

            if self.cal_motion_std > 0:
                motion_norm = max(0.0, (motion_raw - self.cal_motion_mean) / self.cal_motion_std)
            else:
                motion_norm = 0.0
            motion_norm = min(motion_norm, 1.0)

            # EMA
            alpha_top = 0.25
            alpha_motion = 0.30
            self.top_pct_presence[label] = (
                (1 - alpha_top) * self.top_pct_presence[label]
                + alpha_top * top_pct_norm
            )
            self.motion_presence[label] = (
                (1 - alpha_motion) * self.motion_presence[label]
                + alpha_motion * motion_norm
            )
            self.combined_presence[label] = (
                0.6 * self.top_pct_presence[label]
                + 0.4 * self.motion_presence[label]
            )

            # Weighted score (un-normalized, for debugging)
            self.weighted_score[label] = 0.75 * self.weighted_score[label] + 0.25 * float(np.sum(w_delta))
            self.weighted_top_pct[label] = top_pct_val

    def compute_cross_receiver_position(self):
        if not self.calibrated:
            return 0.0, 0.0

        current_amps = {}
        for label in ZONE_ORDER:
            if self.rolling_window[label]:
                current_amps[label] = np.array(self.rolling_window[label][-1])
            else:
                return 0.0, 0.0

        if not all(l in current_amps for l in ZONE_ORDER):
            return 0.0, 0.0

        self.corr_lc = pearson_correlation(current_amps["left"], current_amps["center"])
        self.corr_cr = pearson_correlation(current_amps["center"], current_amps["right"])

        delta_lc = self.cal_corr_lc - self.corr_lc
        delta_cr = self.cal_corr_cr - self.corr_cr

        total_delta = abs(delta_lc) + abs(delta_cr)
        if total_delta < 0.02:
            self.corr_differential = 0.0
            return 0.0, 0.0

        self.corr_differential = (delta_lc - delta_cr) / total_delta
        self.corr_smoothed = 0.85 * self.corr_smoothed + 0.15 * self.corr_differential

        confidence = min(1.0, total_delta * 5) * min(1.0, abs(self.corr_smoothed) * 2)
        return self.corr_smoothed, confidence

    def compute_final_position(self):
        if not self.calibrated:
            return 0.0, 0.0

        scores = {l: self.combined_presence[l] for l in ZONE_ORDER}
        total = sum(scores.values())
        if total > 0:
            confidence = {l: scores[l] / total for l in ZONE_ORDER}
        else:
            confidence = {l: 1.0 / 3 for l in ZONE_ORDER}

        zone_x = {"left": -1.0, "center": 0.0, "right": 1.0}
        y_zone = sum(zone_x[l] * confidence[l] for l in ZONE_ORDER)
        zone_conf = max(confidence.values())

        y_corr, corr_conf = self.compute_cross_receiver_position()

        blend_weight = min(0.35, corr_conf * 0.35)
        self.y_position = (1 - blend_weight) * y_zone + blend_weight * y_corr
        self.spatial_confidence = max(zone_conf, corr_conf) * min(1.0, total * 2)

        return self.y_position, self.spatial_confidence


def main():
    import serial

    streams = {}
    for label, port in RECEIVERS.items():
        streams[label] = serial.Serial(port, BAUD, timeout=0.005)
        print(f"[{label}] opened {port}", flush=True)

    tracker = EnhancedSpatialTracker()
    cal_counts = {label: 0 for label in ZONE_ORDER}

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
                parsed = parse_csi_line(raw)
                if not parsed:
                    continue

                cal_counts[label] += 1
                if not tracker.calibrated:
                    tracker.add_calibration_frame(label, parsed["amps"])
                else:
                    tracker.update(label, parsed["amps"])

            if not tracker.calibrated and all(c >= CAL_FRAMES for c in cal_counts.values()):
                tracker.compute_calibration()
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

            y_pos, conf = tracker.compute_final_position()

            print(f"\n--- {elapsed:.1f}s | y={y_pos:+.3f} conf={conf:.3f} ---", flush=True)
            print(
                f"  corr: LC={tracker.corr_lc:.3f}  CR={tracker.corr_cr:.3f}  "
                f"diff={tracker.corr_differential:+.3f}  smoothed={tracker.corr_smoothed:+.3f}",
                flush=True,
            )
            for label in ZONE_ORDER:
                print(
                    f"  {label:6s}: "
                    f"combined={tracker.combined_presence[label]:.3f}  "
                    f"top_pct={tracker.top_pct_presence[label]:.3f}  "
                    f"motion={tracker.motion_presence[label]:.3f}  "
                    f"weighted={tracker.weighted_score[label]:.3f}  "
                    f"top_pct_raw={tracker.weighted_top_pct[label]:.3f}  "
                    f"motion_raw={tracker.motion_raw[label]:.3f}",
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
