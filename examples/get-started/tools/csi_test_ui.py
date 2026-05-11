#!/usr/bin/env python3

import argparse
import ast
import csv
import json
import math
import os
import sys
import time
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets


DEFAULT_RECEIVERS = {
    "left": "/dev/cu.usbmodem1101",
    "center": "/dev/cu.usbmodem101",
    "right": "/dev/cu.usbmodem2101",
}

ZONE_ORDER = ("left", "center", "right")
ZONE_COLORS = {
    "left": QtGui.QColor(204, 63, 47),
    "center": QtGui.QColor(18, 18, 18),
    "right": QtGui.QColor(38, 103, 185),
}


def parse_csi_line(line):
    start = line.find("CSI_DATA")
    if start < 0:
        return None
    try:
        row = next(csv.reader([line[start:].strip()]))
        values = ast.literal_eval(row[-1])
        amps = [math.hypot(values[i + 1], values[i]) for i in range(0, len(values) - 1, 2)]
        if not amps:
            return None
        return {"rssi": int(row[3]), "amps": amps}
    except Exception as e:
        return None
    try:
        row = next(csv.reader([line[start:].strip()]))
        values = json.loads(row[-1])
        amps = [math.hypot(values[i + 1], values[i]) for i in range(0, len(values) - 1, 2)]
        if not amps:
            return None
        return {"rssi": int(row[3]), "amps": amps}
    except Exception:
        return None


def vector_distance(a, b):
    n = min(len(a), len(b))
    return sum(abs(a[i] - b[i]) for i in range(n)) / n if n else 0


class DataCollector(QtCore.QThread):
    status = QtCore.pyqtSignal(str)
    progress = QtCore.pyqtSignal(float)
    finished = QtCore.pyqtSignal(dict)

    def __init__(self, receivers, baud, duration, phase_label):
        super().__init__()
        self.receivers = receivers
        self.baud = baud
        self.duration = duration
        self.phase_label = phase_label
        self.running = True

    def stop(self):
        self.running = False

    def run(self):
        import serial

        streams = {}
        data = {label: {"rssi": [], "amps": [], "mean_amp": []} for label in ZONE_ORDER}
        start_time = time.time()

        try:
            for label, port in self.receivers.items():
                streams[label] = serial.Serial(port, self.baud, timeout=0.005)
                self.status.emit(f"{label} opened")

            while self.running and (time.time() - start_time) < self.duration:
                elapsed = time.time() - start_time
                self.progress.emit(elapsed / self.duration)

                for label, stream in streams.items():
                    line = stream.readline().decode("utf-8", "replace")
                    parsed = parse_csi_line(line)
                    if not parsed:
                        continue

                    data[label]["rssi"].append(parsed["rssi"])
                    data[label]["amps"].append(parsed["amps"])
                    data[label]["mean_amp"].append(sum(parsed["amps"]) / len(parsed["amps"]))

            self.status.emit(f"collecting complete")
            self.finished.emit(data)

        except Exception as exc:
            self.status.emit(f"error: {exc}")
        finally:
            for stream in streams.values():
                try:
                    stream.close()
                except Exception:
                    pass


class TestUI(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CSI Data Collection Test")
        self.resize(700, 500)
        self.setMinimumSize(600, 400)

        self.output_dir = Path("captures/test_session")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.results = {}
        self.current_collector = None

        self.setStyleSheet(
            """
            QWidget { color: rgb(0, 0, 0); }
            QGroupBox {
                border: 1px solid rgba(0, 0, 0, 90);
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 10px;
                font-weight: bold;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QPushButton {
                background: rgb(248, 248, 246);
                border: 1px solid rgba(0, 0, 0, 90);
                border-radius: 3px;
                padding: 8px 16px;
                min-width: 100px;
            }
            QPushButton:disabled { background: rgb(220, 220, 220); }
            QPushButton:hover { background: rgb(240, 240, 240); }
            QLabel { padding: 2px; }
            """
        )

        layout = QtWidgets.QVBoxLayout(self)

        # Phase 1: Baseline
        self.group_baseline = self._make_phase_group("1. Baseline (empty room, stand still)")
        self.slider_baseline = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_baseline.setRange(5, 60)
        self.slider_baseline.setValue(15)
        self.slider_baseline.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.slider_baseline.setTickInterval(10)
        self.btn_baseline = QtWidgets.QPushButton("Start Baseline")
        self.btn_baseline.clicked.connect(self.start_baseline)
        self.label_baseline = QtWidgets.QLabel("Duration: 15s")
        self.progress_baseline = QtWidgets.QProgressBar()
        self.progress_baseline.setRange(0, 100)

        baseline_layout = QtWidgets.QHBoxLayout()
        baseline_layout.addWidget(self.label_baseline)
        baseline_layout.addWidget(self.slider_baseline)
        baseline_layout.addWidget(self.btn_baseline)
        self.group_baseline.setLayout(baseline_layout)
        layout.addWidget(self.progress_baseline)
        layout.addWidget(self.group_baseline)

        # Phase 2: Hand Waving
        self.group_wave = self._make_phase_group("2. Hand Waving (wave hands in front of receivers)")
        self.slider_wave = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_wave.setRange(5, 60)
        self.slider_wave.setValue(15)
        self.slider_wave.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.slider_wave.setTickInterval(10)
        self.btn_wave = QtWidgets.QPushButton("Start Waving")
        self.btn_wave.clicked.connect(self.start_waving)
        self.btn_wave.setEnabled(False)
        self.label_wave = QtWidgets.QLabel("Duration: 15s")
        self.progress_wave = QtWidgets.QProgressBar()
        self.progress_wave.setRange(0, 100)

        wave_layout = QtWidgets.QHBoxLayout()
        wave_layout.addWidget(self.label_wave)
        wave_layout.addWidget(self.slider_wave)
        wave_layout.addWidget(self.btn_wave)
        self.group_wave.setLayout(wave_layout)
        layout.addWidget(self.progress_wave)
        layout.addWidget(self.group_wave)

        # Phase 3: Presence
        self.group_presence = self._make_phase_group("3. Presence (stand in front of receivers, minimal movement)")
        self.slider_presence = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_presence.setRange(5, 60)
        self.slider_presence.setValue(15)
        self.slider_presence.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.slider_presence.setTickInterval(10)
        self.btn_presence = QtWidgets.QPushButton("Start Presence")
        self.btn_presence.clicked.connect(self.start_presence)
        self.btn_presence.setEnabled(False)
        self.label_presence = QtWidgets.QLabel("Duration: 15s")
        self.progress_presence = QtWidgets.QProgressBar()
        self.progress_presence.setRange(0, 100)

        presence_layout = QtWidgets.QHBoxLayout()
        presence_layout.addWidget(self.label_presence)
        presence_layout.addWidget(self.slider_presence)
        presence_layout.addWidget(self.btn_presence)
        self.group_presence.setLayout(presence_layout)
        layout.addWidget(self.progress_presence)
        layout.addWidget(self.group_presence)

        # Results area
        self.results_text = QtWidgets.QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setMaximumHeight(150)
        layout.addWidget(self.results_text)

        # Connect sliders to labels
        self.slider_baseline.valueChanged.connect(lambda v: self.label_baseline.setText(f"Duration: {v}s"))
        self.slider_wave.valueChanged.connect(lambda v: self.label_wave.setText(f"Duration: {v}s"))
        self.slider_presence.valueChanged.connect(lambda v: self.label_presence.setText(f"Duration: {v}s"))

    def _make_phase_group(self, title):
        group = QtWidgets.QGroupBox(title)
        return group

    def start_baseline(self):
        self._run_phase("baseline", self.slider_baseline.value(), self.btn_baseline, self.progress_baseline)

    def start_waving(self):
        self._run_phase("waving", self.slider_wave.value(), self.btn_wave, self.progress_wave)

    def start_presence(self):
        self._run_phase("presence", self.slider_presence.value(), self.btn_presence, self.progress_presence)

    def _run_phase(self, phase_name, duration, button, progress_bar):
        button.setEnabled(False)
        progress_bar.setValue(0)

        self.current_collector = DataCollector(DEFAULT_RECEIVERS, 921600, duration, phase_name)
        self.current_collector.status.connect(lambda s: self._log(f"[{phase_name}] {s}"))
        self.current_collector.progress.connect(lambda p: progress_bar.setValue(int(p * 100)))
        self.current_collector.finished.connect(lambda data: self._phase_complete(phase_name, data, button, progress_bar))
        self.current_collector.start()

    def _phase_complete(self, phase_name, data, button, progress_bar):
        self.results[phase_name] = data
        progress_bar.setValue(100)
        button.setEnabled(True)

        # Save to file
        output_file = self.output_dir / f"{phase_name}.json"
        with open(output_file, "w") as f:
            json.dump({k: {kk: list(vv) for kk, vv in v.items()} for k, v in data.items()}, f, indent=2)

        self._log(f"Saved to {output_file}")

        # Calculate stats
        stats = {}
        for label in ZONE_ORDER:
            d = data[label]
            rssi = d["rssi"]
            mean_amp = d["mean_amp"]
            if rssi:
                stats[label] = {
                    "rssi_mean": sum(rssi) / len(rssi),
                    "rssi_std": self._std(rssi),
                    "mean_amp_mean": sum(mean_amp) / len(mean_amp),
                    "mean_amp_std": self._std(mean_amp),
                }

        self._log(f"\n=== {phase_name.upper()} STATS ===")
        for label, s in stats.items():
            self._log(f"{label}: RSSI={s['rssi_mean']:.1f}±{s['rssi_std']:.1f} | Amp={s['mean_amp_mean']:.2f}±{s['mean_amp_std']:.2f}")

        # Enable next phase
        if phase_name == "baseline":
            self.btn_wave.setEnabled(True)
        elif phase_name == "waving":
            self.btn_presence.setEnabled(True)
        elif phase_name == "presence":
            self._analyze_all()

    def _analyze_all(self):
        self._log("\n=== COMPARISON ANALYSIS ===")

        phases = ["baseline", "waving", "presence"]

        for label in ZONE_ORDER:
            self._log(f"\n--- {label.upper()} ---")

            means = {}
            for phase in phases:
                data = self.results[phase][label]["mean_amp"]
                means[phase] = sum(data) / len(data) if data else 0

            baseline = means["baseline"]
            self._log(f"Baseline mean amp: {baseline:.2f}")
            self._log(f"Waving delta: {means['waving'] - baseline:+.2f} ({100*(means['waving']-baseline)/baseline:+.1f}%)")
            self._log(f"Presence delta: {means['presence'] - baseline:+.2f} ({100*(means['presence']-baseline)/baseline:+.1f}%)")

    def _std(self, values):
        if len(values) < 2:
            return 0
        mean = sum(values) / len(values)
        return math.sqrt(sum((x - mean) ** 2 for x in values) / len(values))

    def _log(self, msg):
        self.results_text.append(msg)
        print(msg)


def main():
    app = QtWidgets.QApplication(sys.argv)
    window = TestUI()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()