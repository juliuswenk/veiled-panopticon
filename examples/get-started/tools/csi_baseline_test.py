#!/usr/bin/env python3

"""Quick CLI test for adaptive baseline vs static baseline comparison."""

import ast
import csv
import math
import sys
import time
from collections import deque

RECEIVERS = {
    "left": "/dev/cu.usbmodem1101",
    "center": "/dev/cu.usbmodem101",
    "right": "/dev/cu.usbmodem2101",
}
BAUD = 921600
CAL_FRAMES = 100
EMIT_INTERVAL = 0.25

BASELINE_ALPHA = 0.005
MOTION_GATE = 0.6


def parse_csi_line(line):
    start = line.find("CSI_DATA")
    if start < 0:
        return None
    try:
        row = next(csv.reader([line[start:].strip()]))
        values = ast.literal_eval(row[-1])
        amps = []
        for i in range(0, len(values) - 1, 2):
            amps.append(math.hypot(values[i + 1], values[i]))
        if not amps:
            return None
        return {"rssi": int(row[3]), "amps": amps}
    except Exception:
        return None


def vec_dist(a, b):
    w = min(len(a), len(b))
    return sum(abs(a[i] - b[i]) for i in range(w)) / w if w else 0.0


def main():
    import serial

    alpha = float(sys.argv[1]) if len(sys.argv) > 1 else BASELINE_ALPHA

    streams = {}
    for label, port in RECEIVERS.items():
        streams[label] = serial.Serial(port, BAUD, timeout=0.005)
        print(f"[{label}] opened {port}", flush=True)

    state = {}
    for label in RECEIVERS:
        state[label] = {
            "frames": [],
            "baseline": None,
            "static_presence": 0.0,
            "adaptive_presence": 0.0,
            "motion_raw": 0.0,
            "baseline_drift": 0.0,
            "prev_amps": None,
            "rows": 0,
        }

    last_emit = 0.0
    started = time.monotonic()

    try:
        while True:
            for label, stream in streams.items():
                raw = stream.readline().decode("utf-8", "replace")
                parsed = parse_csi_line(raw)
                if not parsed:
                    continue
                s = state[label]
                s["rows"] += 1
                amps = parsed["amps"]

                if s["baseline"] is None:
                    s["frames"].append(amps)
                    if len(s["frames"]) >= CAL_FRAMES:
                        s["baseline"] = [
                            sum(f[i] for f in s["frames"]) / len(s["frames"])
                            for i in range(min(len(f) for f in s["frames"]))
                        ]
                        s["initial_baseline"] = list(s["baseline"])
                        s["frames"] = []
                        print(f"[{label}] calibrated", flush=True)
                    continue

                static_delta = vec_dist(amps, s["baseline"])
                motion_raw = vec_dist(amps, s["prev_amps"]) if s["prev_amps"] else 0.0
                s["motion_raw"] = motion_raw

                if alpha > 0 and s["motion_raw"] < MOTION_GATE:
                    w = min(len(s["baseline"]), len(amps))
                    for i in range(w):
                        s["baseline"][i] += alpha * (amps[i] - s["baseline"][i])
                    s["baseline_drift"] = vec_dist(s["baseline"], s["initial_baseline"])

                adaptive_delta = vec_dist(amps, s["baseline"])

                s["static_presence"] = 0.75 * s["static_presence"] + 0.25 * static_delta
                s["adaptive_presence"] = 0.75 * s["adaptive_presence"] + 0.25 * adaptive_delta
                s["prev_amps"] = amps

            now = time.monotonic()
            if now - last_emit < EMIT_INTERVAL:
                continue
            last_emit = now
            elapsed = now - started

            print(f"\n--- {elapsed:.0f}s elapsed ---", flush=True)
            for label in RECEIVERS:
                s = state[label]
                if s["baseline"] is None:
                    print(f"  {label:6s}: calibrating ({len(s['frames'])}/{CAL_FRAMES})", flush=True)
                else:
                    print(
                        f"  {label:6s}: static={s['static_presence']:6.2f}  "
                        f"adaptive={s['adaptive_presence']:6.2f}  "
                        f"motion={s['motion_raw']:5.2f}  "
                        f"drift={s['baseline_drift']:5.2f}  "
                        f"rows={s['rows']}",
                        flush=True,
                    )
    except KeyboardInterrupt:
        print("\nstopping", flush=True)
    finally:
        for s in streams.values():
            s.close()


if __name__ == "__main__":
    main()
