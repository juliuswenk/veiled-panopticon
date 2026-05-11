#!/usr/bin/env python3

"""
Advanced CSI baseline test with:
  1. Rolling window amplitude baseline (median of recent N frames)
  2. Phase-based presence detection (phase variance deviation)
  3. Aggregate metrics (top-percentile subcarrier deviation)

Compares multiple presence estimators side by side against the original
amplitude-vs-static-baseline approach so we can see which actually
separates presence from noise at 6m through a wall.
"""

import ast
import csv
import math
import signal
import sys
import time
from collections import deque
from pathlib import Path

RECEIVERS = {
    "left": "/dev/cu.usbmodem1101",
    "center": "/dev/cu.usbmodem101",
    "right": "/dev/cu.usbmodem2101",
}
BAUD = 921600
CAL_FRAMES = 200
EMIT_INTERVAL = 0.35

ROLLING_WINDOW = 200
PHASE_SMOOTH_WINDOW = 8
TOP_PCT = 0.15
TOP_PCT_NORM_DIVISOR = 120.0
MOTION_NORM_DIVISOR = 40.0
TOP_PCT_EMA_ALPHA = 0.25
MOTION_EMA_ALPHA = 0.30
COMBINED_TOP_PCT_WEIGHT = 0.6


def parse_csi_line(line):
    start = line.find("CSI_DATA")
    if start < 0:
        return None
    try:
        row = next(csv.reader([line[start:].strip()]))
        values = ast.literal_eval(row[-1])
        amps = []
        phases = []
        for i in range(0, len(values) - 1, 2):
            imag = values[i]
            real = values[i + 1]
            amps.append(math.hypot(real, imag))
            phases.append(math.atan2(imag, real))
        if not amps:
            return None
        return {"rssi": int(row[3]), "amps": amps, "phases": phases}
    except Exception:
        return None


def wrap_pi(v):
    while v <= -math.pi:
        v += math.tau
    while v > math.pi:
        v -= math.tau
    return v


def vec_dist(a, b):
    w = min(len(a), len(b))
    return sum(abs(a[i] - b[i]) for i in range(w)) / w if w else 0.0


def median_vec(frames):
    if not frames:
        return []
    width = min(len(f) for f in frames)
    result = []
    for i in range(width):
        col = sorted(frames[j][i] for j in range(len(frames)))
        mid = len(col) // 2
        result.append(col[mid] if len(col) % 2 else (col[mid - 1] + col[mid]) / 2)
    return result


def percentile_val(values, pct):
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(len(ordered) * pct)))
    return ordered[idx]


def mean_std(values):
    if len(values) < 2:
        return 0.0, 0.0
    m = sum(values) / len(values)
    v = sum((x - m) ** 2 for x in values) / len(values)
    return m, math.sqrt(v)


class PhaseBaseline:
    """Tracks per-subcarrier phase via rolling phase-difference baseline.

    Phase wraps, so we track inter-frame phase-difference (wrapped) and
    accumulate its variance. A human in the room creates extra phase
    variance beyond the ambient thermal/clock noise floor.
    """

    def __init__(self, window):
        self.window = window
        self.diff_history = deque(maxlen=window)

    def update(self, phases):
        if self.diff_history:
            prev = self.diff_history[-1]
            w = min(len(phases), len(prev))
            diff = [wrap_pi(phases[i] - prev[i]) for i in range(w)]
        else:
            diff = [0.0] * len(phases)
        self.diff_history.append(phases)
        return diff

    def variance_energy(self):
        if len(self.diff_history) < 5:
            return 0.0
        w = min(len(d) for d in self.diff_history)
        energy = 0.0
        for i in range(w):
            vals = [abs(self.diff_history[j][i]) for j in range(len(self.diff_history))]
            m = sum(vals) / len(vals)
            energy += sum((v - m) ** 2 for v in vals) / len(vals)
        return energy / max(1, w)


class State:
    def __init__(
        self,
        label,
        top_pct_norm_divisor=TOP_PCT_NORM_DIVISOR,
        motion_norm_divisor=MOTION_NORM_DIVISOR,
        top_pct_ema_alpha=TOP_PCT_EMA_ALPHA,
        motion_ema_alpha=MOTION_EMA_ALPHA,
        combined_top_pct_weight=COMBINED_TOP_PCT_WEIGHT,
    ):
        self.label = label
        self.cal_frames = deque(maxlen=CAL_FRAMES)
        self.baseline = None
        self.rolling_window = deque(maxlen=ROLLING_WINDOW)

        self.phase_baseline = PhaseBaseline(PHASE_SMOOTH_WINDOW)

        self.prev_amps = None
        self.rows = 0

        self.orig_static_presence = 0.0
        self.rolling_amp_presence = 0.0
        self.top_pct_presence = 0.0
        self.motion_presence = 0.0
        self.combined_presence = 0.0
        self.motion_raw = 0.0

        self.amp_mean = 0.0
        self.amp_std = 0.0

        self.top_pct_norm_divisor = top_pct_norm_divisor
        self.motion_norm_divisor = motion_norm_divisor
        self.top_pct_ema_alpha = top_pct_ema_alpha
        self.motion_ema_alpha = motion_ema_alpha
        self.combined_top_pct_weight = combined_top_pct_weight

    def update(self, parsed):
        self.rows += 1
        amps = parsed["amps"]
        phases = parsed["phases"]

        self.phase_baseline.update(phases)
        self.amp_mean, self.amp_std = mean_std(amps)

        if self.baseline is None:
            self.cal_frames.append(amps)
            if len(self.cal_frames) >= CAL_FRAMES:
                self.baseline = median_vec(list(self.cal_frames))
                self.cal_frames.clear()
                print(f"[{self.label}] calibrated", flush=True)
            return

        width = min(len(amps), len(self.baseline))

        amp_delta = [abs(amps[i] - self.baseline[i]) for i in range(width)]

        top_k = max(1, int(width * TOP_PCT))
        top_vals = sorted(amp_delta)[-top_k:]

        phase_energy = self.phase_baseline.variance_energy()
        motion_raw = vec_dist(amps, self.prev_amps) if self.prev_amps else 0.0
        self.prev_amps = amps
        self.motion_raw = motion_raw

        self.rolling_window.append(amps)
        rolling_bl = median_vec(list(self.rolling_window))
        rolling_delta = [abs(amps[i] - rolling_bl[i]) for i in range(width)]
        top_roll = sorted(rolling_delta)[-top_k:]

        orig_static = sum(amp_delta) / width
        rolling_amp = sum(rolling_delta) / width
        top_pct = sum(top_vals) / top_k
        top_pct_roll = sum(top_roll) / top_k

        motion_norm = min(motion_raw / self.motion_norm_divisor, 1.0)
        top_pct_norm = min(top_pct / self.top_pct_norm_divisor, 1.0)

        self.orig_static_presence = 0.75 * self.orig_static_presence + 0.25 * orig_static
        self.rolling_amp_presence = 0.75 * self.rolling_amp_presence + 0.25 * rolling_amp
        self.top_pct_presence = (
            (1.0 - self.top_pct_ema_alpha) * self.top_pct_presence
            + self.top_pct_ema_alpha * top_pct_norm
        )
        self.motion_presence = (
            (1.0 - self.motion_ema_alpha) * self.motion_presence
            + self.motion_ema_alpha * motion_norm
        )
        self.combined_presence = (
            self.combined_top_pct_weight * self.top_pct_presence
            + (1.0 - self.combined_top_pct_weight) * self.motion_presence
        )


def main():
    import argparse
    import serial

    parser = argparse.ArgumentParser(description="Advanced CSI baseline test with configurable thresholds.")
    parser.add_argument(
        "--top-pct-norm-divisor",
        type=float,
        default=TOP_PCT_NORM_DIVISOR,
        help="Divisor for top-percentile amplitude normalization (1m default: 120.0, 6m default: 30.0).",
    )
    parser.add_argument(
        "--motion-norm-divisor",
        type=float,
        default=MOTION_NORM_DIVISOR,
        help="Divisor for motion normalization (1m default: 40.0, 6m default: 15.0).",
    )
    parser.add_argument(
        "--top-pct-ema-alpha",
        type=float,
        default=TOP_PCT_EMA_ALPHA,
        help="EMA smoothing for top-percentile presence (0.1=heavy smooth, 0.5=fast).",
    )
    parser.add_argument(
        "--motion-ema-alpha",
        type=float,
        default=MOTION_EMA_ALPHA,
        help="EMA smoothing for motion presence (0.1=heavy smooth, 0.5=fast).",
    )
    parser.add_argument(
        "--combined-top-pct-weight",
        type=float,
        default=COMBINED_TOP_PCT_WEIGHT,
        help="Weight for top-pct in combined score (0.6 = 60% top-pct, 40% motion).",
    )
    args = parser.parse_args()

    streams = {}
    for label, port in RECEIVERS.items():
        streams[label] = serial.Serial(port, BAUD, timeout=0.005)
        print(f"[{label}] opened {port}", flush=True)

    state = {
        label: State(
            label,
            top_pct_norm_divisor=args.top_pct_norm_divisor,
            motion_norm_divisor=args.motion_norm_divisor,
            top_pct_ema_alpha=args.top_pct_ema_alpha,
            motion_ema_alpha=args.motion_ema_alpha,
            combined_top_pct_weight=args.combined_top_pct_weight,
        )
        for label in RECEIVERS
    }
    started = time.monotonic()
    last_emit = 0.0
    running = [True]

    def handle_signal(sig, frame):
        running[0] = False

    signal.signal(signal.SIGINT, handle_signal)

    try:
        while running[0]:
            for label, stream in streams.items():
                raw = stream.readline().decode("utf-8", "replace")
                parsed = parse_csi_line(raw)
                if not parsed:
                    continue
                state[label].update(parsed)

            now = time.monotonic()
            if now - last_emit < EMIT_INTERVAL:
                continue
            last_emit = now
            elapsed = now - started

            print(f"\n--- {elapsed:.0f}s ---", flush=True)
            for label in RECEIVERS:
                s = state[label]
                if s.baseline is None:
                    print(
                        f"  {label:6s}: calibrating ({len(s.cal_frames)}/{CAL_FRAMES})",
                        flush=True,
                    )
                else:
                    print(
                        f"  {label:6s}: "
                        f"orig_static={s.orig_static_presence:6.2f}  "
                        f"rolling_amp={s.rolling_amp_presence:6.2f}  "
                        f"top20pct={s.top_pct_presence:6.3f}  "
                        f"motion={s.motion_presence:5.3f}  "
                        f"combined={s.combined_presence:5.3f}  "
                        f"motion_raw={s.motion_raw:5.2f}  "
                        f"rows={s.rows}",
                        flush=True,
                    )
    except Exception as e:
        print(f"\nerror: {e}", flush=True)
    finally:
        for s in streams.values():
            s.close()
        print("\nstopping", flush=True)


if __name__ == "__main__":
    main()
