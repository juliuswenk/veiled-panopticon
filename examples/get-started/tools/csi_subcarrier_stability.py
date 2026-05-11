#!/usr/bin/env python3

"""
Identify the most stable subcarriers during idle — these will have the best
signal-to-noise ratio for presence detection.
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
FRAMES = 500


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


def subcarrier_cv(values):
    """Coefficient of variation — normalized variance."""
    if not values:
        return float("inf")
    m = sum(values) / len(values)
    if m < 0.01:
        return float("inf")
    var = sum((v - m) ** 2 for v in values) / len(values)
    return math.sqrt(var) / m


def main():
    import serial

    streams = {}
    for label, port in RECEIVERS.items():
        streams[label] = serial.Serial(port, BAUD, timeout=0.005)
        print(f"[{label}] opened {port}", flush=True)

    amp_history = {label: [] for label in RECEIVERS}
    counts = {label: 0 for label in RECEIVERS}
    running = [True]

    def handle_signal(sig, frame):
        running[0] = False

    signal.signal(signal.SIGINT, handle_signal)

    print(f"Collecting {FRAMES} frames per receiver — stay still\n", flush=True)

    try:
        while running[0] and any(c < FRAMES for c in counts.values()):
            for label, stream in streams.items():
                if counts[label] >= FRAMES:
                    continue
                raw = stream.readline().decode("utf-8", "replace")
                parsed = parse_csi_line(raw)
                if not parsed:
                    continue
                amp_history[label].append(parsed["amps"])
                counts[label] += 1

            if sum(1 for c in counts.values() if c >= FRAMES) >= 3:
                break

        for label in RECEIVERS:
            frames = amp_history[label]
            if not frames:
                continue
            width = min(len(f) for f in frames)
            cvs = []
            means = []
            for i in range(width):
                vals = [frames[j][i] for j in range(len(frames))]
                cvs.append(subcarrier_cv(vals))
                means.append(sum(vals) / len(vals))

            # Sort by CV — lowest is most stable
            indexed = sorted(range(width), key=lambda i: cvs[i])
            print(f"\n--- {label} ({len(frames)} frames, {width} subcarriers) ---", flush=True)
            print(f"  {'idx':>4s}  {'CV':>8s}  {'mean':>8s}  {'rank':>4s}", flush=True)
            for rank in range(min(15, width)):
                i = indexed[rank]
                print(f"  {i:4d}  {cvs[i]:8.4f}  {means[i]:8.2f}  #{rank + 1}", flush=True)

            # Worst 5
            print("  ... worst 5:", flush=True)
            for rank in range(5):
                i = indexed[-(rank + 1)]
                print(f"  {i:4d}  {cvs[i]:8.4f}  {means[i]:8.2f}  #worst{rank + 1}", flush=True)

    except Exception as e:
        print(f"\nerror: {e}", flush=True)
    finally:
        for s in streams.values():
            s.close()
        print("\nstopping", flush=True)


if __name__ == "__main__":
    main()
