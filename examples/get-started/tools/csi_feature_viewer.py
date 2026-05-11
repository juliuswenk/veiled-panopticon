#!/usr/bin/env python3

import argparse
import ast
import csv
import math
import socket
import sys
import time
from collections import deque

from PyQt5 import QtCore, QtGui, QtWidgets


DEFAULT_RECEIVERS = {
    "left": "/dev/cu.usbmodem1101",
    "center": "/dev/cu.usbmodem101",
    "right": "/dev/cu.usbmodem2101",
}

ZONE_ORDER = ("left", "center", "right")
ZONE_X = {"left": -1.0, "center": 0.0, "right": 1.0}
ZONE_COLORS = {
    "left": QtGui.QColor(204, 63, 47),
    "center": QtGui.QColor(18, 18, 18),
    "right": QtGui.QColor(38, 103, 185),
}


class UdpLineStream:
    def __init__(self, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", int(port)))
        self.sock.settimeout(0.005)

    def readline(self):
        try:
            data, _addr = self.sock.recvfrom(8192)
            return data
        except socket.timeout:
            return b""

    def close(self):
        self.sock.close()


def clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


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
        return {"rssi": int(row[3]), "timestamp": int(row[18]), "amps": amps}
    except Exception:
        return None


class FeatureWorker(QtCore.QThread):
    values = QtCore.pyqtSignal(dict)
    status = QtCore.pyqtSignal(str)
    calibration_requested = QtCore.pyqtSignal(int)

    def __init__(self, receivers, baud, calibration_frames, emit_interval):
        super().__init__()
        self.receivers = receivers
        self.baud = baud
        self.total_calibration_frames = calibration_frames
        self.calibration_frames = self._frames_per_receiver(calibration_frames)
        self.emit_interval = emit_interval
        self.running = True
        self._pending_calibration = None
        self.calibration_requested.connect(self._on_calibration_requested)

    def _frames_per_receiver(self, total_frames):
        return max(1, math.ceil(int(total_frames) / max(1, len(self.receivers))))

    def _on_calibration_requested(self, frames):
        self._pending_calibration = int(frames)

    def stop(self):
        self.running = False

    def _new_state(self, target_frames=None):
        return {
            "baseline_rssi": None,
            "baseline_amp": None,
            "rssi_frames": [],
            "amp_frames": [],
            "rssi_smooth": 0.0,
            "amp_smooth": 0.0,
            "rssi_delta": 0.0,
            "amp_delta": 0.0,
            "frame": 0,
            "rssi": 0,
            "mean_amp": 0.0,
            "calibration_target": target_frames or self.calibration_frames,
        }

    def _reset_state_item(self, item, target_frames):
        item["baseline_rssi"] = None
        item["baseline_amp"] = None
        item["rssi_frames"] = []
        item["amp_frames"] = []
        item["rssi_smooth"] = 0.0
        item["amp_smooth"] = 0.0
        item["rssi_delta"] = 0.0
        item["amp_delta"] = 0.0
        item["frame"] = 0
        item["calibration_target"] = target_frames

    def run(self):
        import serial

        streams = {}
        state = {}
        last_emit = 0.0

        for label, port in self.receivers.items():
            state[label] = self._new_state()

        try:
            for label, port in self.receivers.items():
                if str(port).startswith("udp:"):
                    udp_port = str(port).split(":", 1)[1]
                    streams[label] = UdpLineStream(udp_port)
                    self.status.emit(f"{label} listening on UDP {udp_port}")
                else:
                    streams[label] = serial.Serial(port, self.baud, timeout=0.005)
                    self.status.emit(f"{label} opened on {port}")
            self.status.emit(
                f"calibrating {self.total_calibration_frames} total frames "
                f"({self.calibration_frames} per receiver)"
            )

            while self.running:
                if self._pending_calibration is not None:
                    self.total_calibration_frames = self._pending_calibration
                    self.calibration_frames = self._frames_per_receiver(self.total_calibration_frames)
                    for item in state.values():
                        self._reset_state_item(item, self.calibration_frames)
                    self.status.emit(
                        f"recalibrating {self.total_calibration_frames} total frames "
                        f"({self.calibration_frames} per receiver)"
                    )
                    self._pending_calibration = None

                for label, stream in streams.items():
                    line = stream.readline().decode("utf-8", "replace")
                    parsed = parse_csi_line(line)
                    if not parsed:
                        continue

                    item = state[label]
                    item["frame"] += 1
                    item["rssi"] = parsed["rssi"]
                    mean_amp = sum(parsed["amps"]) / len(parsed["amps"])
                    item["mean_amp"] = mean_amp

                    if item["baseline_rssi"] is None:
                        item["rssi_frames"].append(parsed["rssi"])
                        item["amp_frames"].append(mean_amp)
                        target = item["calibration_target"]
                        if len(item["rssi_frames"]) >= target:
                            item["baseline_rssi"] = sorted(item["rssi_frames"])[len(item["rssi_frames"]) // 2]
                            item["baseline_amp"] = sum(item["amp_frames"]) / len(item["amp_frames"])
                            item["rssi_frames"] = []
                            item["amp_frames"] = []
                            self.status.emit(
                                f"{label} calibrated ({target} frames, "
                                f"rssi={item['baseline_rssi']:.0f}, amp={item['baseline_amp']:.1f})"
                            )
                        continue

                    rssi_delta = parsed["rssi"] - item["baseline_rssi"]
                    amp_delta = mean_amp - item["baseline_amp"]

                    # Smooth the deltas (more smoothing = less jitter)
                    alpha = 0.1
                    item["rssi_delta"] = (1.0 - alpha) * item["rssi_delta"] + alpha * rssi_delta
                    item["amp_delta"] = (1.0 - alpha) * item["amp_delta"] + alpha * amp_delta

                now = time.monotonic()
                if now - last_emit < self.emit_interval:
                    continue
                last_emit = now

                self.values.emit(self._make_payload(state))

        except Exception as exc:
            self.status.emit(f"error: {exc}")
        finally:
            for stream in streams.values():
                try:
                    stream.close()
                except Exception:
                    pass

    def _make_payload(self, state):
        ready = {label: state[label]["baseline_rssi"] is not None for label in ZONE_ORDER}
        progress = {
            label: 1.0 if ready[label]
            else clamp(len(state[label]["rssi_frames"]) / state[label]["calibration_target"])
            for label in ZONE_ORDER
        }

        # Use RSSI delta for confidence (larger negative delta = person is closer)
        # Negative delta means signal dropped (person blocking)
        # Use magnitude of negative RSSI delta as score
        # Person is closest to receiver with LARGEST negative RSSI drop
        # Use max(0, -delta) so only negative drops count
        scores = {label: max(0, -state[label]["rssi_delta"]) for label in ZONE_ORDER}
        total = sum(scores.values())

        confidence = (
            {label: scores[label] / total for label in ZONE_ORDER}
            if total > 0
            else {label: 1.0 / len(ZONE_ORDER) for label in ZONE_ORDER}
        )
        winner = max(confidence, key=confidence.get)
        position = sum(ZONE_X[label] * confidence[label] for label in ZONE_ORDER)
        activity = max(scores.values(), default=0.0)

        return {
            "ready": all(ready.values()),
            "progress": progress,
            "scores": scores,
            "confidence": confidence,
            "winner": winner,
            "position": position,
            "activity": activity,
            "features": {
                label: {
                    "rssi": state[label]["rssi"],
                    "baseline_rssi": state[label]["baseline_rssi"],
                    "rssi_delta": state[label]["rssi_delta"],
                    "amp_delta": state[label]["amp_delta"],
                    "mean_amp": state[label]["mean_amp"],
                    "baseline_amp": state[label]["baseline_amp"],
                    "frame": state[label]["frame"],
                    "calibration_target": state[label]["calibration_target"],
                }
                for label in ZONE_ORDER
            },
        }


class FeatureView(QtWidgets.QWidget):
    def __init__(self, default_calibration_frames):
        super().__init__()
        self.setWindowTitle("CSI Zone Tracker")
        self.resize(900, 560)
        self.setMinimumSize(700, 420)
        self.payload = {
            "ready": False,
            "progress": {label: 0.0 for label in ZONE_ORDER},
            "confidence": {label: 1.0 / len(ZONE_ORDER) for label in ZONE_ORDER},
            "winner": "center",
            "position": 0.0,
            "activity": 0.0,
            "features": {},
        }
        self.confidence_history = {label: deque(maxlen=200) for label in ZONE_ORDER}
        self.calibration_frames = default_calibration_frames
        self.status = "starting"

        self.calibrate_button = QtWidgets.QPushButton("Calibrate", self)
        self.calibrate_button.setFixedSize(100, 28)
        self.calibrate_button.clicked.connect(self.request_calibration)

        self.calibration_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, self)
        self.calibration_slider.setRange(50, 500)
        self.calibration_slider.setSingleStep(10)
        self.calibration_slider.setPageStep(50)
        self.calibration_slider.setValue(self.calibration_frames)
        self.calibration_slider.setFixedWidth(180)
        self.calibration_slider.valueChanged.connect(self.set_calibration_frames)

        self.setStyleSheet(
            """
            QWidget, QComboBox, QPushButton, QSlider { color: rgb(0, 0, 0); }
            QComboBox, QPushButton {
                background: rgb(248, 248, 246);
                border: 1px solid rgba(0, 0, 0, 90);
                border-radius: 3px; padding: 3px 8px;
            }
            QSlider::groove:horizontal { height: 2px; background: rgba(0, 0, 0, 70); }
            QSlider::sub-page:horizontal { background: rgb(0, 0, 0); }
            QSlider::handle:horizontal {
                width: 12px; height: 12px; margin: -5px 0;
                border-radius: 6px; background: rgb(0, 0, 0);
            }
            """
        )

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(33)

    def request_calibration(self):
        frames = int(self.calibration_slider.value())
        self.status = f"calibrating {frames} frames..."
        self.update()
        self.calibration_requested.emit(frames)

    def set_status(self, status):
        self.status = status
        self.update()

    def set_calibration_frames(self, value):
        self.calibration_frames = int(value)
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        margin = 28
        y = self.height() - 42
        self.calibrate_button.move(margin, y - 2)
        self.calibration_slider.move(margin + 110, y + 2)

    def set_values(self, payload):
        self.payload = payload
        if payload.get("ready"):
            for label in ZONE_ORDER:
                self.confidence_history[label].append(payload["confidence"].get(label, 0.0))
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = self.rect()
        painter.fillRect(rect, QtGui.QColor(248, 248, 246))

        margin = 28
        header_h = 56
        top = margin
        self.draw_header(painter, QtCore.QRectF(margin, top, rect.width() - 2 * margin, header_h))

        row_top = top + header_h + 18
        row_h = 100
        self.draw_zone_panel(painter, QtCore.QRectF(margin, row_top, rect.width() - 2 * margin, row_h))

        debug_top = row_top + row_h + 14
        debug_h = 70
        self.draw_debug(painter, QtCore.QRectF(margin, debug_top, rect.width() - 2 * margin, debug_h))

        chart_top = debug_top + debug_h + 14
        chart_h = max(60, rect.height() - chart_top - 60)
        self.draw_curves(painter, QtCore.QRectF(margin, chart_top, rect.width() - 2 * margin, chart_h))

        self.draw_controls_labels(painter)
        if not self.payload.get("ready"):
            self.draw_calibration(painter, rect)

    def draw_header(self, painter, rect):
        painter.setPen(QtGui.QColor(20, 20, 20))
        title = QtGui.QFont("Helvetica Neue", 22)
        title.setWeight(QtGui.QFont.Medium)
        painter.setFont(title)
        painter.drawText(rect, QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop, "CSI Zone Tracker")

        small = QtGui.QFont("Menlo", 11)
        painter.setFont(small)
        painter.setPen(QtGui.QColor(70, 70, 70))
        if self.payload.get("ready"):
            text = (
                f"winner {self.payload['winner']}   "
                f"position {self.payload['position']:+.2f}   "
                f"activity {self.payload['activity']:.1f} dB drop"
            )
        else:
            text = self.status
        painter.drawText(rect.adjusted(0, 30, 0, 0), QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop, text)

    def draw_zone_panel(self, painter, rect):
        self.draw_panel_outline(painter, rect)
        confidence = self.payload.get("confidence", {})
        zone_centers = {
            "left": rect.left() + rect.width() * 0.18,
            "center": rect.left() + rect.width() * 0.5,
            "right": rect.left() + rect.width() * 0.82,
        }
        baseline_y = rect.bottom() - 24
        max_bar_h = rect.height() - 40

        for label in ZONE_ORDER:
            value = confidence.get(label, 0.0)
            x = zone_centers[label]
            color = ZONE_COLORS[label]
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor(color.red(), color.green(), color.blue(), 46))
            painter.drawRoundedRect(QtCore.QRectF(x - 34, baseline_y - max_bar_h, 68, max_bar_h), 3, 3)
            painter.setBrush(color)
            painter.drawRoundedRect(QtCore.QRectF(x - 34, baseline_y - max_bar_h * value, 68, max_bar_h * value), 3, 3)
            painter.setPen(QtGui.QColor(20, 20, 20))
            painter.setFont(QtGui.QFont("Menlo", 10))
            painter.drawText(QtCore.QRectF(x - 58, baseline_y + 4, 116, 18), QtCore.Qt.AlignCenter, f"{label} {value:.2f}")

    def draw_debug(self, painter, rect):
        self.draw_panel_outline(painter, rect)
        if not self.payload.get("ready"):
            return

        feat = self.payload.get("features", {})
        scores = self.payload.get("scores", {})

        # Draw scores (RSSI delta magnitude) prominently
        for idx, label in enumerate(ZONE_ORDER):
            f = feat.get(label, {})
            rssi = f.get("rssi", 0)
            base = f.get("baseline_rssi", 0)
            delta = f.get("rssi_delta", 0)
            score = scores.get(label, 0)

            x = rect.left() + 14 + (idx * (rect.width() // 3))
            w = rect.width() // 3 - 14

            # Zone label
            painter.setFont(QtGui.QFont("Helvetica Neue", 12, QtGui.QFont.Bold))
            painter.setPen(ZONE_COLORS[label])
            painter.drawText(QtCore.QRectF(x, rect.top() + 8, w, 20), QtCore.Qt.AlignLeft, label.upper())

            # RSSI value
            painter.setFont(QtGui.QFont("Menlo", 10))
            painter.setPen(QtGui.QColor(40, 40, 40))
            painter.drawText(QtCore.QRectF(x, rect.top() + 28, w, 16), QtCore.Qt.AlignLeft, f"RSSI: {rssi} dBm")

            # Baseline
            painter.setPen(QtGui.QColor(100, 100, 100))
            painter.drawText(QtCore.QRectF(x, rect.top() + 44, w, 16), QtCore.Qt.AlignLeft, f"Base: {base} dBm")

            # Delta (the key metric!)
            delta = f.get("rssi_delta", 0)
            if delta < -3:
                color = QtGui.QColor(200, 0, 0)  # Red for significant drop
            elif delta < -1:
                color = QtGui.QColor(180, 100, 0)  # Orange
            else:
                color = QtGui.QColor(60, 60, 60)

            painter.setFont(QtGui.QFont("Menlo", 11, QtGui.QFont.Bold))
            painter.setPen(color)
            painter.drawText(QtCore.QRectF(x, rect.top() + 60, w, 18), QtCore.Qt.AlignLeft, f"Δ: {delta:+.1f} dB")

    def draw_curves(self, painter, rect):
        self.draw_panel_outline(painter, rect)
        painter.setFont(QtGui.QFont("Helvetica Neue", 12))
        painter.setPen(QtGui.QColor(20, 20, 20))
        painter.drawText(rect.adjusted(14, 6, -14, 0), QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop, "zone confidence")

        plot = rect.adjusted(18, 26, -18, -14)
        painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 35), 1))
        for i in range(4):
            y = plot.top() + plot.height() * i / 3
            painter.drawLine(QtCore.QPointF(plot.left(), y), QtCore.QPointF(plot.right(), y))

        for label in ZONE_ORDER:
            history = self.confidence_history[label]
            if len(history) < 2:
                continue
            color = ZONE_COLORS[label]
            points = []
            for idx, val in enumerate(history):
                x = plot.left() + plot.width() * idx / (history.maxlen - 1)
                y = plot.bottom() - plot.height() * val
                points.append(QtCore.QPointF(x, y))
            path = QtGui.QPainterPath(points[0])
            for p in points[1:]:
                path.lineTo(p)
            pen = QtGui.QPen(color, 2.0)
            pen.setCapStyle(QtCore.Qt.RoundCap)
            painter.setPen(pen)
            painter.drawPath(path)

    def draw_controls_labels(self, painter):
        painter.setFont(QtGui.QFont("Helvetica Neue", 10))
        painter.setPen(QtGui.QColor(80, 80, 80))
        painter.drawText(
            QtCore.QPointF(self.calibration_slider.x(), self.calibration_slider.y() - 8),
            f"total frames {self.calibration_frames} ({math.ceil(self.calibration_frames / len(ZONE_ORDER))} each)",
        )

    def draw_calibration(self, painter, rect):
        progress = self.payload.get("progress", {})
        value = sum(progress.get(label, 0.0) for label in ZONE_ORDER) / len(ZONE_ORDER)
        bar = QtCore.QRectF(rect.width() * 0.24, rect.height() - 30, rect.width() * 0.52, 3)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(0, 0, 0, 26))
        painter.drawRect(bar)
        painter.setBrush(QtGui.QColor(0, 0, 0, 150))
        painter.drawRect(QtCore.QRectF(bar.left(), bar.top(), bar.width() * value, bar.height()))

    def draw_panel_outline(self, painter, rect):
        painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 36), 1))
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawRoundedRect(rect, 4, 4)

    calibration_requested = QtCore.pyqtSignal(int)


def parse_receivers(args):
    receivers = dict(DEFAULT_RECEIVERS)
    for item in args.receiver or []:
        label, port = item.split("=", 1)
        if label not in ZONE_ORDER:
            raise ValueError(f"Unknown receiver label: {label}")
        receivers[label] = port
    return receivers


def main():
    parser = argparse.ArgumentParser(description="CSI zone tracker using RSSI delta.")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--calibration-frames", type=int, default=250)
    parser.add_argument("--emit-interval", type=float, default=0.08)
    parser.add_argument("--receiver", action="append", help="Override a receiver port, e.g. left=/dev/cu.usbmodem1101")
    args = parser.parse_args()

    app = QtWidgets.QApplication(sys.argv)
    view = FeatureView(args.calibration_frames)
    worker = FeatureWorker(
        receivers=parse_receivers(args),
        baud=args.baud,
        calibration_frames=args.calibration_frames,
        emit_interval=args.emit_interval,
    )
    worker.values.connect(view.set_values)
    worker.status.connect(view.set_status)
    worker.status.connect(lambda msg: print(msg, flush=True))
    view.calibration_requested.connect(worker.calibration_requested)
    app.aboutToQuit.connect(worker.stop)

    view.show()
    worker.start()
    result = app.exec_()
    worker.stop()
    worker.wait(1500)
    return result


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
