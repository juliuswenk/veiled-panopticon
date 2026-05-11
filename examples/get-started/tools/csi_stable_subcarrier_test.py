#!/usr/bin/env python3

"""
Presence detection using only the most stable subcarriers.
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
ROLLING_WINDOW = 200
STABLE_COUNT = 15
TOP_PCT = 0.20

STABLE_SUBCARRIERS = {
    "left": [149, 158, 150, 151, 155, 156, 157, 152, 147, 144, 146, 160, 148, 8, 159],
    "center": [9, 10, 7, 11, 8, 6, 158, 12, 157, 155, 148, 160, 153, 156, 151],
    "right": [166, 165, 164, 167, 162, 163, 168, 161, 169, 160, 170, 159, 158, 84, 83],
}


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


def masked_values(amps, indices):
    return [amps[i] for i in indices if i < len(amps)]


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
        self.stable_indices = STABLE_SUBCARRIERS.get(label, list(range(192)))
        self.cal_frames = deque(maxlen=CAL_FRAMES)
        self.cal_stable_frames = deque(maxlen=CAL_FRAMES)
        self.baseline = None
        self.baseline_stable = None
        self.rolling_window = deque(maxlen=ROLLING_WINDOW)
        self.prev_amps = None
        self.prev_stable = None
        self.top_pct_static = 0.0
        self.top_pct_rolling = 0.0
        self.motion_stable = 0.0
        self.motion_all = 0.0
        self.top_pct_norm = 0.0
        self.motion_norm = 0.0
        self.combined = 0.0
        self.calibrated = False

    def update(self, parsed):
        amps = parsed["amps"]
        stable = masked_values(amps, self.stable_indices)

        if not self.calibrated:
            self.cal_frames.append(amps)
            self.cal_stable_frames.append(stable)
            if len(self.cal_frames) >= CAL_FRAMES:
                self.baseline = median_vec(list(self.cal_frames))
                self.baseline_stable = median_vec(list(self.cal_stable_frames))
                self.cal_frames.clear()
                self.cal_stable_frames.clear()
                self.calibrated = True
                print(f"[{self.label}] calibrated", flush=True)
            return

        width_stable = min(len(stable), len(self.baseline_stable))

        # Static baseline deviation (stable subcarriers only)
        stable_delta = [abs(stable[i] - self.baseline_stable[i]) for i in range(width_stable)]
        top_static = top_pct_mean(stable_delta, TOP_PCT)
        self.top_pct_static = 0.75 * self.top_pct_static + 0.25 * top_static

        # Rolling baseline deviation (stable subcarriers only)
        self.rolling_window.append(stable)
        if len(self.rolling_window) >= 30:
            rolling_bl = median_vec(list(self.rolling_window))
            rw = min(len(stable), len(rolling_bl))
            rolling_delta = [abs(stable[i] - rolling_bl[i]) for i in range(rw)]
            top_rolling = top_pct_mean(rolling_delta, TOP_PCT)
            self.top_pct_rolling = 0.75 * self.top_pct_rolling + 0.25 * top_rolling

        # Motion on stable subcarriers
        motion_s = vec_dist(stable, self.prev_stable) if self.prev_stable else 0.0
        self.prev_stable = stable
        self.motion_stable = 0.7 * self.motion_stable + 0.3 * motion_s

        # Motion on all subcarriers
        motion_a = vec_dist(amps, self.prev_amps) if self.prev_amps else 0.0
        self.prev_amps = amps
        self.motion_all = 0.7 * self.motion_all + 0.3 * motion_a

        # Normalized combined score
        top_norm = min(self.top_pct_rolling / 10.0, 1.0)
        mot_norm = min(self.motion_stable / 10.0, 1.0)
        self.top_pct_norm = top_norm
        self.motion_norm = mot_norm
        self.combined = 0.6 * top_norm + 0.4 * mot_norm


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
                if not s.calibrated:
                    print(f"  {label:6s}: calibrating ({len(s.cal_frames)}/{CAL_FRAMES})", flush=True)
                else:
                    print(
                        f"  {label:6s}: "
                        f"static={s.top_pct_static:6.2f}  "
                        f"rolling={s.top_pct_rolling:6.2f}  "
                        f"mot_stable={s.motion_stable:5.2f}  "
                        f"mot_all={s.motion_all:5.2f}  "
                        f"combined={s.combined:.3f}",
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
