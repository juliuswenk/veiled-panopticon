#!/usr/bin/env python3

import argparse
import ast
import csv
import json
import math
import socket
import sys
import time
from collections import deque

import numpy as np

from PyQt5 import QtCore, QtGui, QtWidgets


DEFAULT_RECEIVERS = {
    "left": "/dev/cu.usbmodem1101",
    "center": "/dev/cu.usbmodem101",
    "right": "/dev/cu.usbmodem2101",
}

ZONE_ORDER = ("left", "center", "right")

ROLLING_WINDOW = 150
TOP_PCT = 0.20
TOP_PCT_NORM_DIVISOR = 120.0
MOTION_NORM_DIVISOR = 40.0
TOP_PCT_EMA_ALPHA = 0.25
MOTION_EMA_ALPHA = 0.30
COMBINED_TOP_PCT_WEIGHT = 0.6


def clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def compute_subcarrier_weights(frames):
    if len(frames) < 10:
        return None
    arr = np.array(frames)
    means = np.mean(arr, axis=0)
    stds = np.std(arr, axis=0)
    min_mean = max(0.1, np.percentile(means, 10))
    cov = stds / np.maximum(means, min_mean)
    n = len(cov)
    weight_sum = np.sum(cov)
    if weight_sum > 0:
        return (cov / weight_sum) * n
    return np.ones(n)


def parse_csi_line(line):
    start = line.find("CSI_DATA")
    if start < 0:
        return None
    try:
        row = next(csv.reader([line[start:].strip()]))
        values = ast.literal_eval(row[-1])
        amps = [
            math.hypot(values[i + 1], values[i])
            for i in range(0, len(values) - 1, 2)
        ]
        if not amps:
            return None
        return {
            "rssi": int(row[3]),
            "timestamp": int(row[18]),
            "mean_amp": sum(amps) / len(amps),
            "amps": amps,
        }
    except Exception:
        return None


def average_vector(frames):
    width = min(len(frame) for frame in frames)
    return [
        sum(frame[i] for frame in frames) / len(frames)
        for i in range(width)
    ]


def vector_distance(a, b):
    width = min(len(a), len(b))
    if width == 0:
        return 0.0
    return sum(abs(a[i] - b[i]) for i in range(width)) / width


def median_vector(frames):
    if not frames:
        return []
    width = min(len(f) for f in frames)
    result = []
    for i in range(width):
        col = sorted(frames[j][i] for j in range(len(frames)))
        mid = len(col) // 2
        result.append(col[mid] if len(col) % 2 else (col[mid - 1] + col[mid]) / 2)
    return result


def top_percentile_mean(values, pct):
    if not values:
        return 0.0
    top_k = max(1, int(len(values) * pct))
    top_vals = sorted(values)[-top_k:]
    return sum(top_vals) / top_k


def pearson_correlation(a, b):
    n = min(len(a), len(b))
    if n < 10:
        return 0.0
    a_arr = np.array(a[:n])
    b_arr = np.array(b[:n])
    a_mean = np.mean(a_arr)
    b_mean = np.mean(b_arr)
    a_std = np.std(a_arr)
    b_std = np.std(b_arr)
    if a_std < 1e-6 or b_std < 1e-6:
        return 0.0
    return float(np.mean((a_arr - a_mean) * (b_arr - b_mean)) / (a_std * b_std))


class MultiCsiWorker(QtCore.QThread):
    values = QtCore.pyqtSignal(dict)
    status = QtCore.pyqtSignal(str)

    def __init__(
        self,
        receivers,
        baud,
        calibration_frames,
        activity_scale,
        emit_interval,
        score_alpha,
        top_pct_norm_divisor=TOP_PCT_NORM_DIVISOR,
        motion_norm_divisor=MOTION_NORM_DIVISOR,
        top_pct_ema_alpha=TOP_PCT_EMA_ALPHA,
        motion_ema_alpha=MOTION_EMA_ALPHA,
        combined_top_pct_weight=COMBINED_TOP_PCT_WEIGHT,
    ):
        super().__init__()
        self.receivers = receivers
        self.baud = baud
        self.calibration_frames = calibration_frames
        self.activity_scale = activity_scale
        self.emit_interval = emit_interval
        self.score_alpha = score_alpha
        self.running = True
        self.top_pct_norm_divisor = top_pct_norm_divisor
        self.motion_norm_divisor = motion_norm_divisor
        self.top_pct_ema_alpha = top_pct_ema_alpha
        self.motion_ema_alpha = motion_ema_alpha
        self.combined_top_pct_weight = combined_top_pct_weight
        self.cal_corr_lc = 0.0
        self.cal_corr_cr = 0.0
        self.corr_smoothed = 0.0

    def stop(self):
        self.running = False

    def run(self):
        import serial

        streams = {}
        state = {
            label: {
                "baseline_frames": [],
                "baseline": None,
                "score": 0.0,
                "raw": 0.0,
                "previous_amps": None,
                "rolling_window": deque(maxlen=ROLLING_WINDOW),
                "top_pct_presence": 0.0,
                "motion_presence": 0.0,
                "combined_presence": 0.0,
                "subcarrier_weights": None,
                "rows": 0,
                "rssi": 0,
            }
            for label in ZONE_ORDER
        }
        last_emit = 0.0

        try:
            for label, port in self.receivers.items():
                streams[label] = serial.Serial(port, self.baud, timeout=0.005)
                self.status.emit(f"{label} opened on {port}")

            while self.running:
                for label, stream in streams.items():
                    raw_line = stream.readline().decode("utf-8", "replace")
                    parsed = parse_csi_line(raw_line)
                    if not parsed:
                        continue

                    item = state[label]
                    item["rows"] += 1
                    item["rssi"] = parsed["rssi"]
                    amps = parsed["amps"]

                    if item["baseline"] is None:
                        item["baseline_frames"].append(amps)
                        if len(item["baseline_frames"]) >= self.calibration_frames:
                            item["baseline"] = average_vector(item["baseline_frames"])
                            item["subcarrier_weights"] = compute_subcarrier_weights(item["baseline_frames"])
                            cal_frames = item["baseline_frames"]
                            item["top_pct_divisor"] = self.top_pct_norm_divisor
                            item["motion_divisor"] = self.motion_norm_divisor
                            if len(cal_frames) >= 10:
                                frames = [np.array(f) for f in cal_frames]
                                top_vals, motion_vals = [], []
                                for i in range(30, min(len(frames), 200)):
                                    window = frames[max(0, i - 30):i]
                                    if len(window) < 10:
                                        continue
                                    rolling_bl = np.median(np.array(window), axis=0)
                                    rw = min(len(frames[i]), len(rolling_bl))
                                    rolling_delta = np.abs(frames[i][:rw] - rolling_bl[:rw])
                                    w = item["subcarrier_weights"]
                                    if w is not None:
                                        w_delta = rolling_delta * w[:rw]
                                        top_vals.append(top_percentile_mean(w_delta, TOP_PCT))
                                    else:
                                        top_vals.append(top_percentile_mean(rolling_delta, TOP_PCT))
                                    if i > 30:
                                        motion_vals.append(float(np.mean(np.abs(frames[i] - frames[i - 1]))))
                                if top_vals:
                                    s = sorted(top_vals)
                                    p95_top = s[min(len(s) - 1, int(0.95 * len(s)))]
                                    item["top_pct_divisor"] = max(p95_top * 4.0, 1.0)
                                if motion_vals:
                                    s = sorted(motion_vals)
                                    p95_motion = s[min(len(s) - 1, int(0.95 * len(s)))]
                                    item["motion_divisor"] = max(p95_motion * 4.0, 1.0)
                            item["baseline_frames"] = []
                            self.status.emit(f"{label} calibrated (top_div={item['top_pct_divisor']:.1f} motion_div={item['motion_divisor']:.1f})")
                        continue

                    motion_raw = (
                        vector_distance(amps, item["previous_amps"])
                        if item["previous_amps"]
                        else 0.0
                    )
                    item["previous_amps"] = amps
                    item["raw"] = vector_distance(amps, item["baseline"])
                    item["score"] = (
                        (1.0 - self.score_alpha) * item["score"]
                        + self.score_alpha * item["raw"]
                    )

                    item["rolling_window"].append(amps)
                    if len(item["rolling_window"]) >= 30:
                        rolling_bl = median_vector(list(item["rolling_window"]))
                        rw = min(len(amps), len(rolling_bl))
                        rolling_delta = np.array([abs(amps[i] - rolling_bl[i]) for i in range(rw)])

                        weights = item.get("subcarrier_weights")
                        if weights is not None:
                            w_delta = rolling_delta * weights[:rw]
                            top_pct_val = top_percentile_mean(w_delta, TOP_PCT)
                        else:
                            top_pct_val = top_percentile_mean(rolling_delta, TOP_PCT)

                        top_pct_norm = min(top_pct_val / item.get("top_pct_divisor", self.top_pct_norm_divisor), 1.0)
                        motion_norm = min(motion_raw / item.get("motion_divisor", self.motion_norm_divisor), 1.0)
                        motion_norm = min(motion_raw / self.motion_norm_divisor, 1.0)
                        item["top_pct_presence"] = (
                            (1.0 - self.top_pct_ema_alpha) * item["top_pct_presence"]
                            + self.top_pct_ema_alpha * top_pct_norm
                        )
                        item["motion_presence"] = (
                            (1.0 - self.motion_ema_alpha) * item["motion_presence"]
                            + self.motion_ema_alpha * motion_norm
                        )
                        item["combined_presence"] = (
                            self.combined_top_pct_weight * item["top_pct_presence"]
                            + (1.0 - self.combined_top_pct_weight) * item["motion_presence"]
                        )

                now = time.monotonic()
                if now - last_emit < self.emit_interval:
                    continue
                last_emit = now

                if self.cal_corr_lc == 0.0 and all(
                    state[l]["baseline"] is not None for l in ZONE_ORDER
                ):
                    last_amps = {
                        l: state[l].get("previous_amps") for l in ZONE_ORDER
                        if state[l].get("previous_amps")
                    }
                    if len(last_amps) == 3:
                        self.cal_corr_lc = pearson_correlation(
                            last_amps["left"], last_amps["center"]
                        )
                        self.cal_corr_cr = pearson_correlation(
                            last_amps["center"], last_amps["right"]
                        )

                self.values.emit(self.make_payload(state))
        except Exception as exc:
            self.status.emit(f"error: {exc}")
        finally:
            for stream in streams.values():
                try:
                    stream.close()
                except Exception:
                    pass

    def make_payload(self, state):
        ready = {
            label: state[label]["baseline"] is not None
            for label in ZONE_ORDER
        }
        progress = {
            label: 1.0
            if ready[label]
            else clamp(len(state[label]["baseline_frames"]) / self.calibration_frames)
            for label in ZONE_ORDER
        }

        scores = {
            label: max(0.0, state[label].get("combined_presence", state[label]["score"]))
            for label in ZONE_ORDER
        }
        total = sum(scores.values())
        if total <= 0:
            confidence = {label: 1.0 / len(ZONE_ORDER) for label in ZONE_ORDER}
        else:
            confidence = {
                label: scores[label] / total
                for label in ZONE_ORDER
            }

        winner = max(confidence, key=confidence.get)
        activity = clamp(max(scores.values(), default=0.0) / self.activity_scale)

        zone_x = {"left": 0.22, "center": 0.5, "right": 0.78}
        position_raw = sum(zone_x[l] * confidence[l] for l in ZONE_ORDER)
        position = position_raw

        if self.cal_corr_lc != 0.0:
            current_amps = {
                l: state[l].get("previous_amps") for l in ZONE_ORDER
                if state[l].get("previous_amps")
            }
            if len(current_amps) == 3:
                corr_lc = pearson_correlation(current_amps["left"], current_amps["center"])
                corr_cr = pearson_correlation(current_amps["center"], current_amps["right"])
                delta_lc = self.cal_corr_lc - corr_lc
                delta_cr = self.cal_corr_cr - corr_cr
                total_delta = abs(delta_lc) + abs(delta_cr)
                if total_delta >= 0.02:
                    corr_diff = (delta_lc - delta_cr) / total_delta
                    self.corr_smoothed = 0.85 * self.corr_smoothed + 0.15 * corr_diff
                    corr_conf = min(1.0, total_delta * 5) * min(1.0, abs(self.corr_smoothed) * 2)
                    blend = min(0.35, corr_conf * 0.35)
                    corr_pos = 0.5 + self.corr_smoothed * 0.28
                    position = (1 - blend) * position_raw + blend * corr_pos

        return {
            "ready": all(ready.values()),
            "progress": progress,
            "scores": scores,
            "confidence": confidence,
            "winner": winner,
            "activity": activity,
            "position": position,
            "rows": {label: state[label]["rows"] for label in ZONE_ORDER},
            "rssi": {label: state[label]["rssi"] for label in ZONE_ORDER},
        }


class UdpStreamer:
    def __init__(self, host="127.0.0.1", port=8888):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addr = (host, port)

    def send(self, payload):
        if not payload.get("ready"):
            return
        msg = json.dumps({
            "t": round(time.time(), 3),
            "zones": {
                label: {
                    "c": round(payload["confidence"].get(label, 0.0), 3),
                    "s": round(payload["scores"].get(label, 0.0), 3),
                    "p": round(payload.get("position", 0.5), 3) if label == "center" else 0.0,
                }
                for label in ZONE_ORDER
            },
            "winner": payload["winner"],
            "pos": round(payload.get("position", 0.5), 4),
            "conf": round(max(payload["confidence"].values()), 3),
            "act": round(payload["activity"], 3),
        }).encode("utf-8")
        try:
            self.sock.sendto(msg, self.addr)
        except OSError:
            pass

    def close(self):
        self.sock.close()


class ZoneBlobView(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Invisible Waves")
        self.resize(1180, 720)
        self.setMinimumSize(780, 480)
        self.payload = {
            "ready": False,
            "progress": {label: 0.0 for label in ZONE_ORDER},
            "confidence": {label: 1.0 / len(ZONE_ORDER) for label in ZONE_ORDER},
            "winner": "center",
            "activity": 0.0,
        }
        self.blob_x = 0.5
        self.blob_activity = 0.0
        self.confidence_threshold = 0.48
        self.activity_threshold = 0.22
        self.phase = 0.0

        slider_style = (
            """
            QSlider::groove:horizontal {
                height: 2px;
                background: rgba(0, 0, 0, 42);
                border: 0;
            }
            QSlider::sub-page:horizontal {
                background: rgba(0, 0, 0, 150);
            }
            QSlider::handle:horizontal {
                width: 12px;
                height: 12px;
                margin: -5px 0;
                border-radius: 6px;
                background: rgb(0, 0, 0);
            }
            """
        )
        self.confidence_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, self)
        self.confidence_slider.setRange(25, 85)
        self.confidence_slider.setValue(int(self.confidence_threshold * 100))
        self.confidence_slider.setFixedSize(230, 22)
        self.confidence_slider.setToolTip("zone confidence threshold")
        self.confidence_slider.valueChanged.connect(self.set_confidence_threshold)
        self.confidence_slider.setStyleSheet(slider_style)

        self.activity_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, self)
        self.activity_slider.setRange(5, 70)
        self.activity_slider.setValue(int(self.activity_threshold * 100))
        self.activity_slider.setFixedSize(230, 22)
        self.activity_slider.setToolTip("absolute activity threshold")
        self.activity_slider.valueChanged.connect(self.set_activity_threshold)
        self.activity_slider.setStyleSheet(slider_style)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(33)

    def set_values(self, payload):
        self.payload = payload
        self.update()

    def set_confidence_threshold(self, value):
        self.confidence_threshold = value / 100.0
        self.update()

    def set_activity_threshold(self, value):
        self.activity_threshold = value / 100.0
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        margin = 34
        self.confidence_slider.move(
            self.width() - self.confidence_slider.width() - margin,
            self.height() - 68,
        )
        self.activity_slider.move(
            self.width() - self.activity_slider.width() - margin,
            self.height() - 30,
        )

    def tick(self):
        zone_x = {"left": 0.22, "center": 0.5, "right": 0.78}
        confidence = self.payload.get("confidence", {})
        winner = self.payload.get("winner", "center")
        activity = self.payload.get("activity", 0.0)
        payload_position = self.payload.get("position")
        max_confidence = max(
            (confidence.get(label, 0.0) for label in ZONE_ORDER),
            default=0.0,
        )
        if (
            max_confidence < self.confidence_threshold
            or activity < self.activity_threshold
        ):
            activity = 0.0

        if payload_position is not None and activity > 0:
            target_x = 0.5 + (payload_position - 0.5) * clamp(activity * 1.35)
        else:
            weighted_x = sum(
                zone_x[label] * confidence.get(label, 0.0)
                for label in ZONE_ORDER
            )
            winner_x = zone_x.get(winner, 0.5)
            target_x = 0.76 * winner_x + 0.24 * weighted_x
            target_x = 0.5 + (target_x - 0.5) * clamp(activity * 1.35)

        self.blob_x += (target_x - self.blob_x) * (0.10 + 0.18 * activity)
        self.blob_activity += (activity - self.blob_activity) * 0.22
        self.phase += 0.025 + 0.045 * self.blob_activity
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = self.rect()
        painter.fillRect(rect, QtGui.QColor(255, 255, 255))

        if self.should_draw_blob():
            self.draw_blob(painter, rect)
        self.draw_confidence_curve(painter, rect)
        self.draw_threshold_control(painter, rect)

        if not self.payload.get("ready", False):
            self.draw_calibration_progress(painter, rect)

    def should_draw_blob(self):
        confidence = self.payload.get("confidence", {})
        max_confidence = max(
            (confidence.get(label, 0.0) for label in ZONE_ORDER),
            default=0.0,
        )
        activity = self.payload.get("activity", 0.0)
        return (
            self.payload.get("ready", False)
            and max_confidence >= self.confidence_threshold
            and activity >= self.activity_threshold
        )

    def draw_blob(self, painter, rect):
        width = rect.width()
        height = rect.height()
        shortest = min(width, height)
        activity = self.blob_activity
        cx = width * self.blob_x
        cy = height * (0.53 + math.sin(self.phase) * 0.008 * activity)
        rx = shortest * (0.065 + 0.045 * activity)
        ry = shortest * (0.28 + 0.13 * activity)
        core_alpha = int(58 + 172 * clamp(activity * 1.2))

        painter.setPen(QtCore.Qt.NoPen)
        layers = 18
        for index in range(layers, -1, -1):
            t = index / layers
            grow = 1.0 + 0.82 * t
            alpha = int(core_alpha * ((1.0 - t) ** 1.45))
            if index == layers:
                alpha = 4
            alpha = clamp(alpha, 0, 238)
            painter.setBrush(QtGui.QColor(0, 0, 0, int(alpha)))
            painter.drawEllipse(
                QtCore.QRectF(
                    cx - rx * grow,
                    cy - ry * grow,
                    rx * 2 * grow,
                    ry * 2 * grow,
                )
            )

    def draw_confidence_curve(self, painter, rect):
        confidence = self.payload.get("confidence", {})
        width = rect.width()
        height = rect.height()
        zone_x = {"left": 0.22, "center": 0.5, "right": 0.78}
        base_y = height * 0.74
        amplitude = height * 0.34
        threshold_y = base_y - amplitude * self.confidence_threshold
        points = [
            QtCore.QPointF(
                width * zone_x[label],
                base_y - amplitude * confidence.get(label, 0.0),
            )
            for label in ZONE_ORDER
        ]

        path = QtGui.QPainterPath(points[0])
        for start, end in ((points[0], points[1]), (points[1], points[2])):
            mid_x = (start.x() + end.x()) / 2
            path.cubicTo(
                QtCore.QPointF(mid_x, start.y()),
                QtCore.QPointF(mid_x, end.y()),
                end,
            )

        painter.setBrush(QtCore.Qt.NoBrush)
        threshold_pen = QtGui.QPen(QtGui.QColor(0, 0, 0, 34), 1)
        threshold_pen.setCapStyle(QtCore.Qt.RoundCap)
        painter.setPen(threshold_pen)
        painter.drawLine(
            QtCore.QPointF(width * 0.18, threshold_y),
            QtCore.QPointF(width * 0.82, threshold_y),
        )

        pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 230), 7)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        pen.setJoinStyle(QtCore.Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)

        pen = QtGui.QPen(QtGui.QColor(0, 0, 0, 225), 2)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        pen.setJoinStyle(QtCore.Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)

        for point in points:
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor(255, 255, 255, 235))
            painter.drawEllipse(point, 6, 6)
            painter.setBrush(QtGui.QColor(0, 0, 0, 225))
            painter.drawEllipse(point, 2.4, 2.4)

    def draw_threshold_control(self, painter, rect):
        font = QtGui.QFont("Helvetica Neue")
        font.setPointSize(10)
        painter.setFont(font)
        painter.setPen(QtGui.QColor(0, 0, 0, 128))
        confidence_rect = QtCore.QRectF(
            self.confidence_slider.x(),
            self.confidence_slider.y() - 18,
            self.confidence_slider.width(),
            16,
        )
        painter.drawText(
            confidence_rect,
            QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter,
            f"confidence {self.confidence_threshold:.2f}",
        )
        activity_rect = QtCore.QRectF(
            self.activity_slider.x(),
            self.activity_slider.y() - 18,
            self.activity_slider.width(),
            16,
        )
        painter.drawText(
            activity_rect,
            QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter,
            f"activity {self.activity_threshold:.2f}",
        )

    def draw_calibration_progress(self, painter, rect):
        progress = self.payload.get("progress", {})
        value = sum(progress.get(label, 0.0) for label in ZONE_ORDER) / len(ZONE_ORDER)
        margin = rect.width() * 0.18
        y = rect.height() * 0.90
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(0, 0, 0, 18))
        painter.drawRoundedRect(
            QtCore.QRectF(margin, y, rect.width() - margin * 2, 2),
            1,
            1,
        )
        painter.setBrush(QtGui.QColor(0, 0, 0, 140))
        painter.drawRoundedRect(
            QtCore.QRectF(margin, y, (rect.width() - margin * 2) * value, 2),
            1,
            1,
        )


def parse_receivers(args):
    receivers = dict(DEFAULT_RECEIVERS)
    for item in args.receiver or []:
        label, port = item.split("=", 1)
        if label not in ZONE_ORDER:
            raise ValueError(f"Unknown receiver label: {label}")
        receivers[label] = port
    return receivers


def main():
    parser = argparse.ArgumentParser(
        description="Minimal live left/center/right CSI blob visualization."
    )
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--calibration-frames", type=int, default=250)
    parser.add_argument("--activity-scale", type=float, default=12.0)
    parser.add_argument("--emit-interval", type=float, default=0.04)
    parser.add_argument("--score-alpha", type=float, default=0.34)
    parser.add_argument(
        "--receiver",
        action="append",
        help="Override a receiver port, for example: left=/dev/cu.usbmodem1101",
    )
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
        help="Weight for top-pct in combined score (0.6 = 60/100 top-pct, 40/100 motion).",
    )
    parser.add_argument("--udp-stream", action="store_true", help="Enable UDP JSON stream for p5.js.")
    parser.add_argument("--udp-port", type=int, default=8888, help="UDP port for JSON stream.")
    parser.add_argument("--udp-host", default="127.0.0.1", help="UDP host for JSON stream.")
    args = parser.parse_args()

    receivers = parse_receivers(args)
    app = QtWidgets.QApplication(sys.argv)
    view = ZoneBlobView()
    worker = MultiCsiWorker(
        receivers=receivers,
        baud=args.baud,
        calibration_frames=args.calibration_frames,
        activity_scale=args.activity_scale,
        emit_interval=args.emit_interval,
        score_alpha=clamp(args.score_alpha, 0.02, 1.0),
        top_pct_norm_divisor=args.top_pct_norm_divisor,
        motion_norm_divisor=args.motion_norm_divisor,
        top_pct_ema_alpha=args.top_pct_ema_alpha,
        motion_ema_alpha=args.motion_ema_alpha,
        combined_top_pct_weight=args.combined_top_pct_weight,
    )
    worker.values.connect(view.set_values)
    worker.status.connect(lambda message: print(message, flush=True))

    udp_streamer = None
    if args.udp_stream:
        udp_streamer = UdpStreamer(host=args.udp_host, port=args.udp_port)
        worker.values.connect(udp_streamer.send)
        print(f"UDP stream active: {args.udp_host}:{args.udp_port}", flush=True)

    app.aboutToQuit.connect(worker.stop)

    view.show()
    worker.start()
    result = app.exec_()
    worker.stop()
    worker.wait(1500)
    if udp_streamer:
        udp_streamer.close()
    return result


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
