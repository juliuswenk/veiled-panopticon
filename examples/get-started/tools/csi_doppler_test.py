#!/usr/bin/env python3

"""
Doppler FFT-based motion detection.

Instead of measuring amplitude deviation, compute the FFT of each subcarrier's
amplitude over time. Human motion creates characteristic frequency components
(0.5-10 Hz), while ambient noise is broadband.

This approach is more robust because:
1. It operates in the frequency domain, separating signal from noise
2. It looks at temporal patterns rather than instantaneous values
3. Human motion has a characteristic frequency signature
"""

import ast
import csv
import math
import signal
import time
from collections import deque

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    print("WARNING: numpy not available — using pure Python FFT (slow)")

RECEIVERS = {
    "left": "/dev/cu.usbmodem1101",
    "center": "/dev/cu.usbmodem101",
    "right": "/dev/cu.usbmodem2101",
}
BAUD = 921600
EMIT_INTERVAL = 0.35
DOPPLER_WINDOW = 64  # frames for FFT
SAMPLE_RATE = 65  # approximate frames per second
DOPPLER_BAND = (0.5, 8.0)  # Hz — human motion frequency range


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


def compute_doppler_energy(history, band, sample_rate):
    """Compute energy in a specific frequency band from amplitude history.
    
    history: list of amplitude values for a single subcarrier over time
    band: (low_hz, high_hz) frequency range to measure
    sample_rate: frames per second
    """
    n = len(history)
    if n < 8:
        return 0.0
    
    if HAS_NUMPY:
        # Use numpy FFT
        signal_data = np.array(history)
        signal_data -= np.mean(signal_data)  # Remove DC
        spectrum = np.abs(np.fft.rfft(signal_data))
        
        # Frequency bins
        freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)
        
        # Find bins in the target band
        low_idx = np.searchsorted(freqs, band[0])
        high_idx = np.searchsorted(freqs, band[1])
        
        if low_idx >= high_idx:
            return 0.0
        
        band_energy = np.sum(spectrum[low_idx:high_idx])
        total_energy = np.sum(spectrum[1:])  # Skip DC
        
        if total_energy < 1e-10:
            return 0.0
        
        return band_energy / total_energy
    else:
        # Pure Python — simplified
        # Just use variance as a proxy for motion energy
        mean = sum(history) / n
        var = sum((x - mean) ** 2 for x in history) / n
        return var


class DopplerTracker:
    """Tracks Doppler energy for each subcarrier."""
    
    def __init__(self, n_subcarriers, window=DOPPLER_WINDOW):
        self.n_subcarriers = n_subcarriers
        self.window = window
        self.history = [deque(maxlen=window) for _ in range(n_subcarriers)]
        self.doppler_energy = 0.0
        self.prev_amps = None
    
    def update(self, amps):
        for i in range(min(len(amps), self.n_subcarriers)):
            self.history[i].append(amps[i])
        
        if len(self.history[0]) >= 8:
            # Compute Doppler energy for a subset of subcarriers
            # Use the most active ones (highest variance)
            energies = []
            for i in range(0, min(len(amps), self.n_subcarriers), 4):  # Every 4th subcarrier
                hist = list(self.history[i])
                energy = compute_doppler_energy(hist, DOPPLER_BAND, SAMPLE_RATE)
                energies.append(energy)
            
            if energies:
                # Average Doppler energy
                avg_energy = sum(energies) / len(energies)
                # EMA smoothing
                self.doppler_energy = 0.8 * self.doppler_energy + 0.2 * avg_energy
        
        return self.doppler_energy


class State:
    def __init__(self, label):
        self.label = label
        self.tracker = None
        self.calibrated = False
        self.doppler_ema = 0.0
        self.motion_raw = 0.0
        self.prev_amps = None
    
    def update(self, parsed):
        amps = parsed["amps"]
        
        if not self.calibrated:
            # Initialize tracker on first frame
            self.tracker = DopplerTracker(len(amps))
            self.calibrated = True
            print(f"[{self.label}] ready", flush=True)
        
        motion = (
            sum(abs(amps[i] - self.prev_amps[i]) for i in range(min(len(amps), len(self.prev_amps)))) / min(len(amps), len(self.prev_amps))
            if self.prev_amps
            else 0.0
        )
        self.prev_amps = amps
        self.motion_raw = motion
        
        doppler = self.tracker.update(amps)
        self.doppler_ema = 0.85 * self.doppler_ema + 0.15 * doppler
        
        return self.doppler_ema


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
                    print(f"  {label:6s}: initializing", flush=True)
                else:
                    print(
                        f"  {label:6s}: "
                        f"doppler={s.doppler_ema:.4f}  "
                        f"motion={s.motion_raw:6.2f}  "
                        f"window={s.tracker.window}  "
                        f"fill={len(s.tracker.history[0])}/{s.tracker.window}",
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
