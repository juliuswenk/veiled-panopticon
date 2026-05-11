#!/usr/bin/env python3

"""
Rate-of-change based presence detection.

Instead of measuring absolute deviation from baseline (which is drowned by noise),
measure how FAST the baseline is changing. Human movement causes rapid baseline
shifts; idle noise drifts slowly.
"""

import ast
import csv
import math
import signal
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
LONG_WINDOW = 500
SHORT_WINDOW = 10
TOP_PCT = 0.10


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


def vec_dist(a, b):
    w = min(len(a), len(b))
    return sum(abs(a[i] - b[i]) for i in range(w)) / w if w else 0.0


def top_pct_mean(values, pct):
    if not values:
        return 0.0
    top_k = max(1, int(len(values) * pct))
    return sum(sorted(values)[-top_k:]) / top_k


class State:
    def __init__(self, label):
        self.label = label
        self.cal_frames = deque(maxlen=CAL_FRAMES)
        self.long_window = deque(maxlen=LONG_WINDOW)
        self.short_baseline_history = deque(maxlen=20)
        self.baseline = None
        self.prev_amps = None
        self.presence_ema = 0.0
        self.prev_long_bl = None
        self.raw_top = 0.0
        self.raw_bl_change = 0.0
        self.raw_drift = 0.0

    def update(self, parsed):
        amps = parsed["amps"]

        if self.baseline is None:
            self.cal_frames.append(amps)
            if len(self.cal_frames) >= CAL_FRAMES:
                self.baseline = median_vec(list(self.cal_frames))
                self.cal_frames.clear()
                print(f"[{self.label}] calibrated", flush=True)
            return

        width = min(len(amps), len(self.baseline))

        motion_raw = vec_dist(amps, self.prev_amps) if self.prev_amps else 0.0
        self.prev_amps = amps

        self.long_window.append(amps)

        if len(self.long_window) >= SHORT_WINDOW:
            short_bl = median_vec(list(self.long_window)[-SHORT_WINDOW:])
            self.short_baseline_history.append(short_bl)

            if len(self.short_baseline_history) >= 3:
                # Rate of change: distance between recent short baselines
                recent_bl = list(self.short_baseline_history)
                bl_changes = [
                    vec_dist(recent_bl[i], recent_bl[i - 1])
                    for i in range(1, len(recent_bl))
                ]
                bl_change_rate = sum(bl_changes) / len(bl_changes)
            else:
                bl_change_rate = 0.0

            # Also: deviation of current frame from long-window median
            long_bl = median_vec(list(self.long_window))
            amp_delta = [abs(amps[i] - long_bl[i]) for i in range(width)]
            top_val = top_pct_mean(amp_delta, TOP_PCT)

            # Deviation of long baseline from original calibration
            long_drift = vec_dist(long_bl, self.baseline)

            self.raw_top = top_val
            self.raw_bl_change = bl_change_rate
            self.raw_drift = long_drift



def main():
    import serial

    streams = {}
    for label, port in RECEIVERS.items():
        streams[label] = serial.Serial(port, BAUD, timeout=0.005)
        print(f"[{label}] opened {port}", flush=True)

    state = {label: State(label) for label in RECEIVERS}
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

            print(f"\n--- {elapsed:.1f}s ---", flush=True)
            for label in RECEIVERS:
                s = state[label]
                if s.baseline is None:
                    print(f"  {label:6s}: calibrating ({len(s.cal_frames)}/{CAL_FRAMES})", flush=True)
                else:
                    print(
                        f"  {label:6s}: "
                        f"top={s.raw_top:6.2f}  "
                        f"bl_change={s.raw_bl_change:6.2f}  "
                        f"drift={s.raw_drift:6.2f}  "
                        f"long_win={len(s.long_window)}",
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
