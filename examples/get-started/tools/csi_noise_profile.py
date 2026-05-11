#!/usr/bin/env python3

"""Idle noise characterization — run for 30s with NO movement."""

import ast
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
ROLLING_WINDOW = 200
TOP_PCT = 0.15
EMIT_INTERVAL = 0.5


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


def top_pct_mean(values, pct):
    if not values:
        return 0.0
    top_k = max(1, int(len(values) * pct))
    return sum(sorted(values)[-top_k:]) / top_k


def vec_dist(a, b):
    w = min(len(a), len(b))
    return sum(abs(a[i] - b[i]) for i in range(w)) / w if w else 0.0


class State:
    def __init__(self, label):
        self.label = label
        self.cal_frames = deque(maxlen=CAL_FRAMES)
        self.baseline = None
        self.rolling_window = deque(maxlen=ROLLING_WINDOW)
        self.prev_amps = None
        self.top_pct_values = []
        self.motion_values = []
        self.rolling_top_values = []
        self.rolling_motion_values = []

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

        amp_delta = [abs(amps[i] - self.baseline[i]) for i in range(width)]
        top_val = top_pct_mean(amp_delta, TOP_PCT)
        motion_raw = vec_dist(amps, self.prev_amps) if self.prev_amps else 0.0
        self.prev_amps = amps

        self.top_pct_values.append(top_val)
        self.motion_values.append(motion_raw)

        self.rolling_window.append(amps)
        if len(self.rolling_window) >= 30:
            rolling_bl = median_vec(list(self.rolling_window))
            rw = min(len(amps), len(rolling_bl))
            rolling_delta = [abs(amps[i] - rolling_bl[i]) for i in range(rw)]
            r_top = top_pct_mean(rolling_delta, TOP_PCT)
            r_motion = vec_dist(amps, self.rolling_window[-2]) if len(self.rolling_window) >= 2 else 0.0
            self.rolling_top_values.append(r_top)
            self.rolling_motion_values.append(r_motion)

    def stats(self, values):
        if not values:
            return 0, 0, 0, 0
        return len(values), min(values), sum(values) / len(values), max(values)


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

    print("STAY COMPLETELY STILL — characterizing idle noise\n", flush=True)

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

            for label in RECEIVERS:
                s = state[label]
                if s.baseline is None:
                    print(f"  {label:6s}: calibrating ({len(s.cal_frames)}/{CAL_FRAMES})", flush=True)
                    continue

                n, mn, avg, mx = s.stats(s.top_pct_values)
                n2, mn2, avg2, mx2 = s.stats(s.rolling_top_values)
                n3, mn3, avg3, mx3 = s.stats(s.motion_values)
                n4, mn4, avg4, mx4 = s.stats(s.rolling_motion_values)

                print(
                    f"\n--- {elapsed:.0f}s [{label}] ---",
                    f"static_top: n={n} min={mn:.2f} avg={avg:.2f} max={mx:.2f}",
                    f"rolling_top: n={n2} min={mn2:.2f} avg={avg2:.2f} max={mx2:.2f}",
                    f"static_motion: n={n3} min={mn3:.2f} avg={avg3:.2f} max={mx3:.2f}",
                    f"rolling_motion: n={n4} min={mn4:.2f} avg={avg4:.2f} max={mx4:.2f}",
                    sep="\n  ",
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
