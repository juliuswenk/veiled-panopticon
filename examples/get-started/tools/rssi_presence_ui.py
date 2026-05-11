#!/usr/bin/env python3

import argparse
import ast
import csv
import json
import math
import queue
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PyQt5 import QtCore, QtGui, QtWidgets


ZONE_ORDER = ("left", "center", "right")
DEFAULT_RECEIVERS = {
    "left": "/dev/cu.usbmodem101",
    "center": "/dev/cu.usbmodem1101",
    "right": "/dev/cu.usbmodem2101",
}
DEFAULT_MIN_RSSI = -80


def clamp(value, low, high):
    return max(low, min(high, value))


def median(values):
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def mad(values, center):
    if not values or center is None:
        return None
    return median([abs(value - center) for value in values])


def robust_scale(values, center, floor):
    spread = mad(values, center)
    if spread is None:
        return floor
    return max(spread * 1.4826, floor)


def parse_csi(line):
    start = line.find("CSI_DATA")
    if start < 0:
        return None
    try:
        row = next(csv.reader([line[start:].strip()]))
        values = ast.literal_eval(row[-1])
        raw_amps = [math.hypot(values[i + 1], values[i]) for i in range(0, len(values) - 1, 2)]
        amps = list(raw_amps)
        if not amps:
            return None
        amps = sorted(amps)
        trim = max(1, int(len(amps) * 0.1))
        trimmed = amps[trim:-trim] if len(amps) > trim * 2 else amps
        mean_amp = sum(trimmed) / len(trimmed)
        return {"rssi": int(row[3]), "mean_amp": mean_amp, "amps": raw_amps}
    except Exception:
        return None


class MotionVarianceFilter:
    """Python version of MotionDetector's moving-average variance integrator."""

    def __init__(self, sample_size=64, average_size=16, integrator=3, autoregressive=True):
        self.sample_size = max(4, int(sample_size))
        self.average_size = clamp(int(average_size), 2, self.sample_size)
        self.integrator = clamp(int(integrator), 1, self.sample_size)
        self.autoregressive = bool(autoregressive)
        self.samples = deque(maxlen=self.sample_size)
        self.variances = deque(maxlen=self.sample_size)
        self.ar_value = 0.0

    def reset(self):
        self.samples.clear()
        self.variances.clear()
        self.ar_value = 0.0

    def process(self, sample):
        self.samples.append(float(sample))
        if len(self.samples) < self.sample_size:
            return None

        recent = list(self.samples)[-self.average_size :]
        average = sum(recent) / len(recent)
        variance_sample = (float(sample) - average) ** 2
        self.variances.append(variance_sample)

        variance_integral = sum(list(self.variances)[-self.integrator :])
        if self.autoregressive:
            self.ar_value = (variance_integral + self.ar_value) / 2.0
            return self.ar_value
        return variance_integral


class ScalarKalman:
    def __init__(self, process_noise=0.04, measurement_noise=0.85):
        self.process_noise = float(process_noise)
        self.measurement_noise = float(measurement_noise)
        self.value = None
        self.covariance = 1.0

    def reset(self):
        self.value = None
        self.covariance = 1.0

    def filter(self, measurement):
        measurement = float(measurement)
        if self.value is None:
            self.value = measurement
            return self.value

        self.covariance += self.process_noise
        gain = self.covariance / (self.covariance + self.measurement_noise)
        self.value += gain * (measurement - self.value)
        self.covariance *= 1.0 - gain
        return self.value


def output_payload_from_state(state, threshold, flip_lr=False, active_map=None, thresholds=None, release_ratios=None):
    model = state.get("__model")
    raw_presence = {
        zone: float(state.get(zone, {}).get("presence", 0.0))
        for zone in ZONE_ORDER
    }

    if model and isinstance(model.get("confidence"), dict):
        model_confidence = model.get("confidence", {})
        channels = {
            zone: round(clamp(float(model_confidence.get(zone, 0.0)), 0.0, 1.0), 4)
            for zone in ZONE_ORDER
        }
        winner = model.get("winner", "baseline")
        confidence = round(clamp(float(model_confidence.get(winner, 0.0)), 0.0, 1.0), 4)
        clear = round(clamp(float(model_confidence.get("baseline", 0.0)), 0.0, 1.0), 4)
        source = "model"
    else:
        total = sum(max(value, 0.0) for value in raw_presence.values())
        channels = {
            zone: round(max(raw_presence[zone], 0.0) / total, 4) if total > 0 else 0.0
            for zone in ZONE_ORDER
        }
        winner = max(channels, key=channels.get)
        confidence = channels[winner]
        if isinstance(threshold, dict):
            clear = 1.0 if all(raw_presence[zone] < threshold.get(zone, 0.0) for zone in ZONE_ORDER) else 0.0
        else:
            clear = 1.0 if max(raw_presence.values(), default=0.0) < threshold else 0.0
        source = "presence"

    states = {
        zone: bool(active_map.get(zone, False)) if isinstance(active_map, dict) else False
        for zone in ZONE_ORDER
    }
    zones = {
        zone: {
            "c": channels[zone],
            "raw": round(raw_presence[zone], 4),
            "rssi": state.get(zone, {}).get("rssi"),
            "active": states[zone],
            "threshold": round(float(thresholds.get(zone, 0.0)), 4) if isinstance(thresholds, dict) else None,
            "release_ratio": round(float(release_ratios.get(zone, 0.0)), 4) if isinstance(release_ratios, dict) else None,
            "raw_presence": round(float(state.get(zone, {}).get("raw_presence", 0.0)), 4),
            "presence_baseline": (
                round(float(state.get(zone, {}).get("presence_baseline")), 4)
                if state.get(zone, {}).get("presence_baseline") is not None
                else None
            ),
            "calibration_kind": state.get(zone, {}).get("calibration_kind"),
            "calibration_progress": round(float(state.get(zone, {}).get("calibration_progress", 0.0)), 4),
            "noise_floor": round(float(state.get(zone, {}).get("noise_floor", 0.0)), 4),
            "smoothing": round(float(state.get(zone, {}).get("smoothing", 0.0)), 4),
            "motion_weight": round(float(state.get(zone, {}).get("motion_weight", 0.0)), 4),
            "connected": bool(state.get(zone, {}).get("connected", False)),
        }
        for zone in ZONE_ORDER
    }

    if flip_lr:
        channels = dict(channels)
        zones = dict(zones)
        channels["left"], channels["right"] = channels["right"], channels["left"]
        zones["left"], zones["right"] = zones["right"], zones["left"]
        states = dict(states)
        states["left"], states["right"] = states["right"], states["left"]
        if winner == "left":
            winner = "right"
        elif winner == "right":
            winner = "left"

    return {
        "t": round(time.time(), 3),
        "source": source,
        "mirrored": bool(flip_lr),
        "channels": channels,
        "raw_channels": dict(channels),
        "states": states,
        "zones": zones,
        "winner": winner,
        "confidence": confidence,
        "clear": clear,
    }


class OutputStabilizer:
    def __init__(
        self,
        enter_threshold=0.42,
        exit_threshold=0.28,
        min_gap=0.10,
        strong_threshold=0.65,
        attack=0.22,
        release=0.07,
    ):
        self.enter_threshold = float(enter_threshold)
        self.exit_threshold = float(exit_threshold)
        self.min_gap = float(min_gap)
        self.strong_threshold = float(strong_threshold)
        self.attack = float(attack)
        self.release = float(release)
        self.active = False
        self.channels = {zone: 0.0 for zone in ZONE_ORDER}

    def update(self, payload):
        raw_channels = {
            zone: clamp(float(payload["channels"].get(zone, 0.0)), 0.0, 1.0)
            for zone in ZONE_ORDER
        }
        ranked = sorted(raw_channels.items(), key=lambda item: item[1], reverse=True)
        best_zone, best_value = ranked[0]
        second_value = ranked[1][1] if len(ranked) > 1 else 0.0
        gap = best_value - second_value
        clear = float(payload.get("clear", 0.0))

        ambiguous = gap < self.min_gap
        weak_ambiguous = ambiguous and best_value < self.strong_threshold

        if self.active:
            if best_value <= self.exit_threshold or clear >= 0.70 or weak_ambiguous:
                self.active = False
        elif best_value >= self.enter_threshold and clear < 0.70 and not weak_ambiguous:
            self.active = True

        target = raw_channels if self.active else {zone: 0.0 for zone in ZONE_ORDER}
        stabilized = {}
        for zone in ZONE_ORDER:
            previous = self.channels[zone]
            alpha = self.attack if target[zone] > previous else self.release
            stabilized[zone] = previous + alpha * (target[zone] - previous)

        output_channels = {
            zone: round(clamp(stabilized[zone], 0.0, 1.0), 4)
            for zone in ZONE_ORDER
        }

        self.channels = stabilized
        payload = dict(payload)
        payload["raw_channels"] = raw_channels
        payload["channels"] = output_channels
        payload["active"] = bool(self.active)
        payload["ambiguous"] = bool(ambiguous)
        payload["top_gap"] = round(gap, 4)
        payload["confidence"] = round(max(output_channels.values(), default=0.0), 4)
        payload["clear"] = round(1.0 - payload["confidence"], 4)
        payload["winner"] = best_zone if self.active and not weak_ambiguous else "none"
        payload["zones"] = {
            zone: {
                **payload["zones"].get(zone, {}),
                "c": output_channels[zone],
                "raw_c": round(raw_channels[zone], 4),
            }
            for zone in ZONE_ORDER
        }
        return payload


class SseOutputServer:
    def __init__(self, port):
        self.port = int(port)
        self.clients = []
        self.lock = threading.Lock()
        self.httpd = None
        self.thread = None

    def start(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_OPTIONS(self):
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

            def do_GET(self):
                if self.path not in ("/events", "/"):
                    self.send_error(404)
                    return
                if self.path == "/":
                    self.send_response(200)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"status":"ok","events":"/events"}\n')
                    return

                client_queue = queue.Queue(maxsize=3)
                with owner.lock:
                    owner.clients.append(client_queue)

                self.send_response(200)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()

                try:
                    self.wfile.write(b": connected\n\n")
                    self.wfile.flush()
                    while True:
                        try:
                            payload = client_queue.get(timeout=8)
                            self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                        except queue.Empty:
                            self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
                except Exception:
                    pass
                finally:
                    with owner.lock:
                        if client_queue in owner.clients:
                            owner.clients.remove(client_queue)

            def log_message(self, fmt, *args):
                return

        self.httpd = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def publish(self, payload):
        message = json.dumps(payload, separators=(",", ":"))
        with self.lock:
            clients = list(self.clients)
        for client in clients:
            try:
                if client.full():
                    client.get_nowait()
                client.put_nowait(message)
            except Exception:
                pass

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()


class JsonOutput(QtCore.QObject):
    def __init__(
        self,
        threshold_getter,
        flip_getter,
        stabilizer=None,
        sse_server=None,
        active_getter=None,
        thresholds_getter=None,
        release_ratios_getter=None,
    ):
        super().__init__()
        self.threshold_getter = threshold_getter
        self.flip_getter = flip_getter
        self.stabilizer = stabilizer
        self.sse_server = sse_server
        self.active_getter = active_getter
        self.thresholds_getter = thresholds_getter
        self.release_ratios_getter = release_ratios_getter

    @QtCore.pyqtSlot(dict)
    def send_state(self, state):
        payload = output_payload_from_state(
            state,
            self.threshold_getter(),
            self.flip_getter(),
            self.active_getter() if self.active_getter else None,
            self.thresholds_getter() if self.thresholds_getter else None,
            self.release_ratios_getter() if self.release_ratios_getter else None,
        )
        if self.stabilizer:
            payload = self.stabilizer.update(payload)
        if self.sse_server:
            self.sse_server.publish(payload)


class SerialWorker(QtCore.QThread):
    values = QtCore.pyqtSignal(dict)
    status = QtCore.pyqtSignal(str)
    recalibrate_requested = QtCore.pyqtSignal(int)
    zone_calibration_requested = QtCore.pyqtSignal(dict)
    tuning_changed = QtCore.pyqtSignal(dict)

    def __init__(
        self,
        receivers,
        baud,
        baseline_frames,
        emit_interval,
        min_rssi,
        window_size,
        average_size,
        integrator,
        model_path=None,
        model_window=90,
    ):
        super().__init__()
        self.receivers = receivers
        self.baud = baud
        self.baseline_frames = baseline_frames
        self.emit_interval = emit_interval
        self.min_rssi = min_rssi
        self.window_size = window_size
        self.average_size = average_size
        self.integrator = integrator
        self.zone_model = self._load_zone_model(model_path)
        self.model_window = max(10, int(model_window))
        self.running = True
        self._pending_recalibration = None
        self._pending_zone_calibrations = []
        self.tuning = {
            zone: {"noise_floor": 0.0, "smoothing": 0.24, "motion_weight": 0.58}
            for zone in ZONE_ORDER
        }
        self.recalibrate_requested.connect(self._on_recalibrate_requested)
        self.zone_calibration_requested.connect(self._on_zone_calibration_requested)
        self.tuning_changed.connect(self._on_tuning_changed)

    def _load_zone_model(self, model_path):
        if not model_path:
            return None
        try:
            with open(model_path, "r", encoding="utf-8") as stream:
                model = json.load(stream)
            self.status.emit(f"loaded zone model: {model_path}")
            return model
        except Exception as exc:
            self.status.emit(f"zone model failed: {exc}")
            return None

    def stop(self):
        self.running = False

    def _on_recalibrate_requested(self, frames):
        self._pending_recalibration = max(1, int(frames))

    def _on_zone_calibration_requested(self, request):
        if not isinstance(request, dict):
            return
        zone = request.get("zone")
        kind = request.get("kind")
        if zone not in ZONE_ORDER or kind not in ("clean", "present"):
            return
        self._pending_zone_calibrations.append({
            "zone": zone,
            "kind": kind,
            "frames": max(1, int(request.get("frames", self.baseline_frames))),
        })

    def _on_tuning_changed(self, tuning):
        if not isinstance(tuning, dict):
            return
        for zone, values in tuning.items():
            if zone not in ZONE_ORDER or not isinstance(values, dict):
                continue
            current = self.tuning.setdefault(zone, {})
            current["noise_floor"] = max(0.0, float(values.get("noise_floor", current.get("noise_floor", 0.0))))
            current["smoothing"] = clamp(float(values.get("smoothing", current.get("smoothing", 0.24))), 0.01, 1.0)
            current["motion_weight"] = clamp(float(values.get("motion_weight", current.get("motion_weight", 0.58))), 0.0, 1.0)

    def _new_state(self, port=None):
        return {
            "port": port,
            "connected": bool(port),
            "rssi": None,
            "mean_amp": None,
            "baseline_rssi": None,
            "baseline_amp": None,
            "rssi_scale": 1.0,
            "amp_scale": 1.0,
            "amp_delta": 0.0,
            "rssi_delta": 0.0,
            "rssi_motion": 0.0,
            "amp_motion": 0.0,
            "motion_score": 0.0,
            "raw_presence": 0.0,
            "presence_baseline": None,
            "presence_baseline_samples": [],
            "presence_baseline_target": 0,
            "baseline_target_frames": None,
            "calibration_kind": None,
            "calibration_progress": 0.0,
            "noise_floor": 0.0,
            "smoothing": 0.24,
            "motion_weight": 0.58,
            "presence": 0.0,
            "valid_signal": True,
            "frames": 0,
            "rssi_samples": [],
            "amp_samples": [],
            "history": deque(maxlen=140),
            "model_frames": deque(maxlen=self.model_window),
            "last_seen": 0.0,
            "rssi_filter": MotionVarianceFilter(self.window_size, self.average_size, self.integrator),
            "amp_filter": MotionVarianceFilter(self.window_size, self.average_size, self.integrator),
            "kalman": ScalarKalman(),
        }

    def _reset_baseline(self, state, frames):
        self.baseline_frames = frames
        for item in state.values():
            if not item.get("connected"):
                continue
            item["baseline_rssi"] = None
            item["baseline_amp"] = None
            item["presence"] = 0.0
            item["amp_delta"] = 0.0
            item["rssi_delta"] = 0.0
            item["rssi_motion"] = 0.0
            item["amp_motion"] = 0.0
            item["motion_score"] = 0.0
            item["raw_presence"] = 0.0
            item["presence_baseline"] = None
            item["presence_baseline_samples"] = []
            item["presence_baseline_target"] = 0
            item["baseline_target_frames"] = None
            item["calibration_kind"] = None
            item["calibration_progress"] = 0.0
            item["rssi_filter"].reset()
            item["amp_filter"].reset()
            item["kalman"].reset()
            item["rssi_samples"] = []
            item["amp_samples"] = []
            item["history"].clear()
            item["model_frames"].clear()
        self.status.emit(f"recalibrating baseline over {frames} frames")

    def _start_zone_calibration(self, state, request):
        zone = request["zone"]
        item = state.get(zone)
        if not item or not item.get("connected"):
            self.status.emit(f"{zone} calibration skipped: not connected")
            return

        frames = request["frames"]
        if request["kind"] == "clean":
            item["baseline_rssi"] = None
            item["baseline_amp"] = None
            item["presence"] = 0.0
            item["raw_presence"] = 0.0
            item["presence_baseline"] = None
            item["baseline_target_frames"] = frames
            item["calibration_kind"] = "clean"
            item["calibration_progress"] = 0.0
            item["rssi_filter"].reset()
            item["amp_filter"].reset()
            item["kalman"].reset()
            item["rssi_samples"] = []
            item["amp_samples"] = []
            item["history"].clear()
            self.status.emit(f"{zone}: clean baseline over {frames} frames")
            return

        if item.get("baseline_rssi") is None or item.get("baseline_amp") is None:
            self.status.emit(f"{zone}: present baseline needs clean baseline first")
            return

        item["presence_baseline_samples"] = []
        item["presence_baseline_target"] = frames
        item["calibration_kind"] = "present"
        item["calibration_progress"] = 0.0
        self.status.emit(f"{zone}: present baseline over {frames} frames")

    def _percentile(self, values, pct):
        if not values:
            return 0.0
        ordered = sorted(values)
        idx = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * pct)))
        return ordered[idx]

    def _median(self, values):
        return median(values) if values else 0.0

    def _model_response_vector(self, state):
        if not self.zone_model:
            return None

        vector = []
        receivers = self.zone_model.get("receivers", [])
        baselines = self.zone_model.get("baseline", {})
        for label in receivers:
            item = state.get(label)
            baseline = baselines.get(label)
            if not item or not baseline or len(item["model_frames"]) < 10:
                return None

            frames = list(item["model_frames"])
            medians = baseline.get("median", [])
            scales = baseline.get("scale", [])
            width = min([len(medians), len(scales)] + [len(frame["amps"]) for frame in frames])
            values = []
            for i in range(width):
                if medians[i] <= 2.0:
                    continue
                column = [
                    (frame["amps"][i] - medians[i]) / max(scales[i], 1.0)
                    for frame in frames
                ]
                values.append(self._median(column))

            ordered = sorted(values)
            if ordered:
                for pct in (0.05, 0.15, 0.30, 0.50, 0.70, 0.85, 0.95):
                    vector.append(self._percentile(ordered, pct))
            else:
                vector.extend([0.0] * 7)

            rssi_values = [frame["rssi"] for frame in frames]
            vector.append(baseline.get("rssi_median", 0.0) - self._median(rssi_values))

        return vector

    def _model_estimate(self, state):
        vector = self._model_response_vector(state)
        if not vector:
            return None
        templates = self.zone_model.get("templates", {})
        distances = {}
        for label, template in templates.items():
            width = min(len(vector), len(template))
            if width == 0:
                continue
            distances[label] = math.sqrt(sum((vector[i] - template[i]) ** 2 for i in range(width)))
        if not distances:
            return None

        inv = {label: 1.0 / max(distance, 1e-6) for label, distance in distances.items()}
        total = sum(inv.values()) or 1.0
        confidence = {label: value / total for label, value in inv.items()}
        winner = min(distances, key=distances.get)
        return {
            "winner": winner,
            "confidence": confidence,
            "distances": distances,
        }

    def run(self):
        import serial

        streams = {}
        state = {zone: self._new_state(self.receivers.get(zone)) for zone in ZONE_ORDER}
        last_emit = 0.0

        def open_streams():
            for zone, port in self.receivers.items():
                try:
                    if streams.get(zone) and not streams[zone].is_open:
                        streams[zone].open()
                    elif zone not in streams:
                        streams[zone] = serial.Serial(port, self.baud, timeout=0.005)
                        self.status.emit(f"{zone} opened on {port}")
                        state[zone]["connected"] = True
                except Exception as exc:
                    self.status.emit(f"{zone} open failed: {exc}")
                    state[zone]["connected"] = False

        def safe_read(stream):
            try:
                return stream.readline()
            except Exception:
                return None

        while self.running:
            if self._pending_recalibration is not None:
                self._reset_baseline(state, self._pending_recalibration)
                self._pending_recalibration = None
            while self._pending_zone_calibrations:
                self._start_zone_calibration(state, self._pending_zone_calibrations.pop(0))

            open_streams()
            if not any(s.get("connected") for s in state.values()):
                time.sleep(1)
                continue

            for zone, stream in list(streams.items()):
                if not state[zone].get("connected"):
                    continue

                line = safe_read(stream)
                if line is None:
                    state[zone]["connected"] = False
                    self.status.emit(f"{zone} disconnected, will retry")
                    continue

                parsed = parse_csi(line.decode("utf-8", "replace"))
                if parsed is None:
                    continue

                item = state[zone]
                if parsed["rssi"] == 0 or parsed["rssi"] < self.min_rssi:
                    item["valid_signal"] = False
                    continue

                item["valid_signal"] = True
                item["frames"] += 1
                item["rssi"] = parsed["rssi"]
                item["mean_amp"] = parsed["mean_amp"]
                item["model_frames"].append({"rssi": parsed["rssi"], "amps": parsed["amps"]})
                item["last_seen"] = time.monotonic()

                if item["baseline_rssi"] is None:
                    item["rssi_samples"].append(parsed["rssi"])
                    item["amp_samples"].append(parsed["mean_amp"])
                    target_frames = item.get("baseline_target_frames") or self.baseline_frames
                    item["calibration_progress"] = min(1.0, len(item["rssi_samples"]) / max(target_frames, 1))
                    if len(item["rssi_samples"]) >= target_frames:
                        item["baseline_rssi"] = median(item["rssi_samples"])
                        item["baseline_amp"] = median(item["amp_samples"])
                        item["rssi_scale"] = robust_scale(item["rssi_samples"], item["baseline_rssi"], 1.0)
                        item["amp_scale"] = robust_scale(
                            item["amp_samples"],
                            item["baseline_amp"],
                            max(item["baseline_amp"] * 0.012, 1.0),
                        )
                        item["rssi_samples"] = []
                        item["amp_samples"] = []
                        item["baseline_target_frames"] = None
                        item["calibration_kind"] = None
                        item["calibration_progress"] = 1.0
                        self.status.emit(
                            f"{zone} baseline: RSSI {item['baseline_rssi']:.1f} dBm, amp {item['baseline_amp']:.1f}"
                        )
                    continue

                rssi_drop = max(0.0, item["baseline_rssi"] - parsed["rssi"])
                amp_deviation = abs(parsed["mean_amp"] - item["baseline_amp"])

                rssi_variance = item["rssi_filter"].process(parsed["rssi"])
                amp_variance = item["amp_filter"].process(parsed["mean_amp"])

                rssi_scale = max(item.get("rssi_scale", 1.0), 1.0)
                amp_scale = max(item.get("amp_scale", 1.0), 1.0)

                item["rssi_delta"] = rssi_drop / rssi_scale
                item["amp_delta"] = amp_deviation / amp_scale
                item["rssi_motion"] = 0.0
                item["amp_motion"] = 0.0

                if rssi_variance is not None:
                    item["rssi_motion"] = math.sqrt(max(rssi_variance, 0.0) / self.integrator) / rssi_scale
                if amp_variance is not None:
                    item["amp_motion"] = math.sqrt(max(amp_variance, 0.0) / self.integrator) / amp_scale

                zone_tuning = self.tuning.get(zone, {})
                noise_floor = max(0.0, float(zone_tuning.get("noise_floor", 0.0)))
                smoothing = clamp(float(zone_tuning.get("smoothing", 0.24)), 0.01, 1.0)
                motion_weight = clamp(float(zone_tuning.get("motion_weight", 0.58)), 0.0, 1.0)

                static_score = 0.48 * item["rssi_delta"] + 0.52 * item["amp_delta"]
                motion_score = 0.46 * item["rssi_motion"] + 0.54 * item["amp_motion"]
                item["motion_score"] = motion_score
                combined = (1.0 - motion_weight) * static_score + motion_weight * motion_score
                if item.get("presence_baseline_target", 0) > 0:
                    item["presence_baseline_samples"].append(combined)
                    target = item["presence_baseline_target"]
                    item["calibration_progress"] = min(1.0, len(item["presence_baseline_samples"]) / max(target, 1))
                    if len(item["presence_baseline_samples"]) >= target:
                        item["presence_baseline"] = median(item["presence_baseline_samples"])
                        item["presence_baseline_samples"] = []
                        item["presence_baseline_target"] = 0
                        item["calibration_kind"] = None
                        item["calibration_progress"] = 1.0
                        self.status.emit(f"{zone} present baseline: score {item['presence_baseline']:.2f}")

                filtered = max(0.0, item["kalman"].filter(combined) - noise_floor)
                presence_baseline = item.get("presence_baseline")
                if presence_baseline is not None:
                    denom = max(presence_baseline - noise_floor, 0.1)
                    normalized = clamp((combined - noise_floor) / denom, 0.0, 2.0) * 5.0
                    filtered = max(filtered, normalized)
                item["raw_presence"] = combined
                item["noise_floor"] = noise_floor
                item["smoothing"] = smoothing
                item["motion_weight"] = motion_weight
                item["presence"] += smoothing * (filtered - item["presence"])
                item["presence"] = max(0.0, item["presence"])
                item["history"].append(item["presence"])

            now = time.monotonic()
            if now - last_emit >= self.emit_interval:
                last_emit = now
                model_estimate = self._model_estimate(state)
                if model_estimate:
                    state["__model"] = model_estimate
                self.values.emit(state)


class PresenceView(QtWidgets.QWidget):
    recalibrate_requested = QtCore.pyqtSignal(int)
    zone_calibration_requested = QtCore.pyqtSignal(dict)
    tuning_changed = QtCore.pyqtSignal(dict)

    def __init__(self, threshold, baseline_frames):
        super().__init__()
        self.setWindowTitle("CSI Presence (Amplitude + RSSI)")
        self.resize(980, 790)
        self.setMinimumSize(840, 720)
        self.threshold = float(threshold)
        self.thresholds = {zone: float(threshold) for zone in ZONE_ORDER}
        self.release_ratios = {zone: 0.65 for zone in ZONE_ORDER}
        self.noise_floors = {zone: 0.0 for zone in ZONE_ORDER}
        self.smoothing = {zone: 0.24 for zone in ZONE_ORDER}
        self.motion_weights = {zone: 0.58 for zone in ZONE_ORDER}
        self.baseline_frames = int(baseline_frames)
        self.status = "starting"
        self.state = {zone: self._empty_state() for zone in ZONE_ORDER}
        self.blocked_state = {zone: False for zone in ZONE_ORDER}
        self.flip_output = False

        self.calibrate_button = QtWidgets.QPushButton("Calibrate baseline", self)
        self.calibrate_button.clicked.connect(self.request_recalibration)

        self.flip_checkbox = QtWidgets.QCheckBox("flip output L/R", self)
        self.flip_checkbox.setStyleSheet("color: black;")
        self.flip_checkbox.stateChanged.connect(self.set_flip_output)

        self.baseline_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, self)
        self.baseline_slider.setRange(30, 5000)
        self.baseline_slider.setValue(self.baseline_frames)
        self.baseline_slider.setSingleStep(10)
        self.baseline_slider.setPageStep(50)
        self.baseline_slider.valueChanged.connect(self.set_baseline_frames)

        self.baseline_label = QtWidgets.QLabel(self)
        self.baseline_label.setStyleSheet("color: black;")

        self.threshold_sliders = {}
        self.threshold_labels = {}
        self.release_sliders = {}
        self.release_labels = {}
        self.clean_buttons = {}
        self.present_buttons = {}
        self.noise_floor_sliders = {}
        self.noise_floor_labels = {}
        self.smoothing_sliders = {}
        self.smoothing_labels = {}
        self.motion_weight_sliders = {}
        self.motion_weight_labels = {}
        for zone in ZONE_ORDER:
            clean_button = QtWidgets.QPushButton(f"{zone} clean", self)
            clean_button.clicked.connect(lambda checked=False, z=zone: self.request_zone_calibration(z, "clean"))
            self.clean_buttons[zone] = clean_button

            present_button = QtWidgets.QPushButton(f"{zone} present", self)
            present_button.clicked.connect(lambda checked=False, z=zone: self.request_zone_calibration(z, "present"))
            self.present_buttons[zone] = present_button

            threshold_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, self)
            threshold_slider.setRange(0, 200)
            threshold_slider.setValue(int(self.thresholds[zone] * 10))
            threshold_slider.valueChanged.connect(lambda value, z=zone: self.set_zone_threshold(z, value))
            self.threshold_sliders[zone] = threshold_slider

            threshold_label = QtWidgets.QLabel(self)
            threshold_label.setStyleSheet("color: black;")
            self.threshold_labels[zone] = threshold_label

            release_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, self)
            release_slider.setRange(10, 100)
            release_slider.setValue(int(self.release_ratios[zone] * 100))
            release_slider.valueChanged.connect(lambda value, z=zone: self.set_zone_release_ratio(z, value))
            self.release_sliders[zone] = release_slider

            release_label = QtWidgets.QLabel(self)
            release_label.setStyleSheet("color: black;")
            self.release_labels[zone] = release_label

            noise_floor_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, self)
            noise_floor_slider.setRange(0, 100)
            noise_floor_slider.setValue(int(self.noise_floors[zone] * 10))
            noise_floor_slider.valueChanged.connect(lambda value, z=zone: self.set_zone_noise_floor(z, value))
            self.noise_floor_sliders[zone] = noise_floor_slider

            noise_floor_label = QtWidgets.QLabel(self)
            noise_floor_label.setStyleSheet("color: black;")
            self.noise_floor_labels[zone] = noise_floor_label

            smoothing_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, self)
            smoothing_slider.setRange(1, 100)
            smoothing_slider.setValue(int(self.smoothing[zone] * 100))
            smoothing_slider.valueChanged.connect(lambda value, z=zone: self.set_zone_smoothing(z, value))
            self.smoothing_sliders[zone] = smoothing_slider

            smoothing_label = QtWidgets.QLabel(self)
            smoothing_label.setStyleSheet("color: black;")
            self.smoothing_labels[zone] = smoothing_label

            motion_weight_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal, self)
            motion_weight_slider.setRange(0, 100)
            motion_weight_slider.setValue(int(self.motion_weights[zone] * 100))
            motion_weight_slider.valueChanged.connect(lambda value, z=zone: self.set_zone_motion_weight(z, value))
            self.motion_weight_sliders[zone] = motion_weight_slider

            motion_weight_label = QtWidgets.QLabel(self)
            motion_weight_label.setStyleSheet("color: black;")
            self.motion_weight_labels[zone] = motion_weight_label

        self.setStyleSheet(
            """
            QWidget { background: rgb(250, 250, 248); color: black; }
            QPushButton {
                background: rgb(255, 255, 255);
                border: 1px solid rgba(0, 0, 0, 80);
                border-radius: 4px;
                padding: 4px 10px;
                color: black;
            }
            QSlider::groove:horizontal { height: 2px; background: rgba(0, 0, 0, 70); }
            QSlider::sub-page:horizontal { background: rgb(0, 0, 0); }
            QSlider::handle:horizontal {
                width: 14px; height: 14px; margin: -6px 0;
                border-radius: 7px; background: rgb(0, 0, 0);
            }
            """
        )
        self._update_baseline_label()
        for zone in ZONE_ORDER:
            self._update_zone_control_labels(zone)

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(33)

    def _empty_state(self):
        return {
            "port": None,
            "connected": False,
            "rssi": None,
            "mean_amp": None,
            "baseline_rssi": None,
            "baseline_amp": None,
            "rssi_scale": 1.0,
            "amp_scale": 1.0,
            "amp_delta": 0.0,
            "rssi_delta": 0.0,
            "rssi_motion": 0.0,
            "amp_motion": 0.0,
            "motion_score": 0.0,
            "raw_presence": 0.0,
            "noise_floor": 0.0,
            "smoothing": 0.24,
            "motion_weight": 0.58,
            "presence": 0.0,
            "valid_signal": True,
            "frames": 0,
            "history": deque(maxlen=140),
            "last_seen": 0.0,
        }

    def set_status(self, status):
        self.status = status
        self.update()

    def set_values(self, state):
        self.state = state
        self.update()

    def set_zone_threshold(self, zone, value):
        self.thresholds[zone] = value / 10.0
        self.threshold = max(self.thresholds.values())
        self.blocked_state[zone] = False
        self._update_zone_control_labels(zone)
        self.update()

    def set_zone_release_ratio(self, zone, value):
        self.release_ratios[zone] = value / 100.0
        self._update_zone_control_labels(zone)
        self.update()

    def set_zone_noise_floor(self, zone, value):
        self.noise_floors[zone] = value / 10.0
        self._emit_tuning()
        self._update_zone_control_labels(zone)
        self.update()

    def set_zone_smoothing(self, zone, value):
        self.smoothing[zone] = value / 100.0
        self._emit_tuning()
        self._update_zone_control_labels(zone)
        self.update()

    def set_zone_motion_weight(self, zone, value):
        self.motion_weights[zone] = value / 100.0
        self._emit_tuning()
        self._update_zone_control_labels(zone)
        self.update()

    def set_flip_output(self, value):
        self.flip_output = value == QtCore.Qt.Checked
        self.update()

    def set_baseline_frames(self, value):
        self.baseline_frames = int(value)
        self._update_baseline_label()
        self.update()

    def request_recalibration(self):
        self.status = f"recalibrating baseline over {self.baseline_frames} frames"
        self.recalibrate_requested.emit(self.baseline_frames)
        self.update()

    def request_zone_calibration(self, zone, kind):
        label = "clean baseline" if kind == "clean" else "present baseline"
        self.status = f"{zone}: calibrating {label} over {self.baseline_frames} frames"
        self.zone_calibration_requested.emit({
            "zone": zone,
            "kind": kind,
            "frames": self.baseline_frames,
        })
        self.update()

    def _update_baseline_label(self):
        self.baseline_label.setText(f"baseline frames: {self.baseline_frames}")

    def _update_zone_control_labels(self, zone):
        threshold = self.thresholds[zone]
        release_ratio = self.release_ratios[zone]
        self.threshold_labels[zone].setText(f"{zone} threshold: {threshold:.1f}")
        self.release_labels[zone].setText(f"release: {release_ratio:.2f}x = {threshold * release_ratio:.1f}")
        self.noise_floor_labels[zone].setText(f"noise floor: {self.noise_floors[zone]:.1f}")
        self.smoothing_labels[zone].setText(f"smoothing: {self.smoothing[zone]:.2f}")
        self.motion_weight_labels[zone].setText(f"motion mix: {self.motion_weights[zone]:.2f}")

    def _emit_tuning(self):
        self.tuning_changed.emit({
            zone: {
                "noise_floor": self.noise_floors[zone],
                "smoothing": self.smoothing[zone],
                "motion_weight": self.motion_weights[zone],
            }
            for zone in ZONE_ORDER
        })

    def get_thresholds(self):
        return dict(self.thresholds)

    def get_release_ratios(self):
        return dict(self.release_ratios)

    def get_active_channels(self):
        for zone in ZONE_ORDER:
            self._is_blocked(zone, self.state.get(zone, self._empty_state()))
        return dict(self.blocked_state)

    def _zone_ready(self, item):
        return item.get("baseline_rssi") is not None and item.get("baseline_amp") is not None

    def _is_blocked(self, zone, item):
        if not item.get("connected") or not self._zone_ready(item) or not item.get("valid_signal", True):
            self.blocked_state[zone] = False
            return False

        presence = item.get("presence", 0.0)
        if self.blocked_state.get(zone, False):
            self.blocked_state[zone] = presence >= self.thresholds[zone] * self.release_ratios[zone]
        else:
            self.blocked_state[zone] = presence >= self.thresholds[zone]
        return self.blocked_state[zone]

    def resizeEvent(self, event):
        super().resizeEvent(event)
        y = self.height() - 286
        self.calibrate_button.setGeometry(28, y - 4, 150, 28)
        self.flip_checkbox.setGeometry(194, y - 4, 130, 28)
        self.baseline_label.setGeometry(338, y - 1, 150, 22)
        self.baseline_slider.setGeometry(494, y + 3, self.width() - 522, 24)
        row_y = y + 38
        for idx, zone in enumerate(ZONE_ORDER):
            yy = row_y + idx * 82
            self.clean_buttons[zone].setGeometry(28, yy - 4, 92, 26)
            self.present_buttons[zone].setGeometry(126, yy - 4, 104, 26)
            self.threshold_labels[zone].setGeometry(244, yy - 1, 150, 22)
            self.threshold_sliders[zone].setGeometry(400, yy + 3, 135, 24)
            self.release_labels[zone].setGeometry(550, yy - 1, 160, 22)
            self.release_sliders[zone].setGeometry(718, yy + 3, self.width() - 746, 24)

            yy2 = yy + 26
            self.noise_floor_labels[zone].setGeometry(28, yy2 - 1, 150, 22)
            self.noise_floor_sliders[zone].setGeometry(184, yy2 + 3, 220, 24)
            self.smoothing_labels[zone].setGeometry(424, yy2 - 1, 180, 22)
            self.smoothing_sliders[zone].setGeometry(610, yy2 + 3, self.width() - 638, 24)

            yy3 = yy + 52
            self.motion_weight_labels[zone].setGeometry(28, yy3 - 1, 150, 22)
            self.motion_weight_sliders[zone].setGeometry(184, yy3 + 3, self.width() - 212, 24)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor(250, 250, 248))

        self._draw_header(painter)
        self._draw_receivers(painter)
        self._draw_indicator(painter)

    def _draw_header(self, painter):
        painter.setPen(QtGui.QColor(0, 0, 0))
        title = QtGui.QFont("Helvetica Neue", 24)
        title.setWeight(QtGui.QFont.Medium)
        painter.setFont(title)
        painter.drawText(QtCore.QRectF(28, 22, self.width() - 56, 34), QtCore.Qt.AlignLeft, "CSI Presence")

        painter.setFont(QtGui.QFont("Menlo", 11))
        painter.setPen(QtGui.QColor(80, 80, 80))
        painter.drawText(QtCore.QRectF(30, 58, self.width() - 60, 20), QtCore.Qt.AlignLeft, self.status)

        model = self.state.get("__model")
        if model:
            winner = model.get("winner", "--")
            confidence_map = model.get("confidence", {})
            confidence = confidence_map.get(winner, 0.0) if isinstance(confidence_map, dict) else 0.0
            if winner == "baseline":
                text = f"model: clear  {confidence:.2f}"
            else:
                text = f"model: {winner.upper()}  {confidence:.2f}"
            painter.setPen(QtGui.QColor(0, 0, 0))
            painter.drawText(QtCore.QRectF(30, 78, self.width() - 60, 20), QtCore.Qt.AlignLeft, text)

    def _draw_receivers(self, painter):
        top = 104
        h = 224
        gap = 16
        w = (self.width() - 56 - 2 * gap) / 3.0
        for idx, zone in enumerate(ZONE_ORDER):
            rect = QtCore.QRectF(28 + idx * (w + gap), top, w, h)
            self._draw_receiver_card(painter, rect, zone)

    def _draw_receiver_card(self, painter, rect, zone):
        item = self.state.get(zone, self._empty_state())
        active = item.get("connected")
        ready = self._zone_ready(item)
        presence = item.get("presence", 0.0)
        blocked = self._is_blocked(zone, item)

        painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 38), 1))
        painter.setBrush(QtGui.QColor(255, 255, 255))
        painter.drawRoundedRect(rect, 6, 6)

        painter.setFont(QtGui.QFont("Helvetica Neue", 16, QtGui.QFont.Medium))
        painter.setPen(QtGui.QColor(0, 0, 0))
        painter.drawText(rect.adjusted(16, 14, -16, 0), QtCore.Qt.AlignLeft, zone.upper())

        painter.setFont(QtGui.QFont("Menlo", 11))
        painter.setPen(QtGui.QColor(90, 90, 90))
        port = item.get("port") or "not connected"
        painter.drawText(rect.adjusted(16, 42, -16, 0), QtCore.Qt.AlignLeft, port)

        rssi = item.get("rssi")
        mean_amp = item.get("mean_amp")
        baseline_rssi = item.get("baseline_rssi")
        baseline_amp = item.get("baseline_amp")

        rssi_text = "--" if rssi is None else f"{rssi} dBm"
        amp_text = "--" if mean_amp is None else f"{mean_amp:.1f}"

        if not active:
            baseline_rssi_text = "not connected"
            baseline_amp_text = "not connected"
        elif item.get("frames", 0) == 0:
            baseline_rssi_text = "waiting data"
            baseline_amp_text = "waiting data"
        elif not ready:
            baseline_rssi_text = "calibrating"
            baseline_amp_text = "calibrating"
        else:
            baseline_rssi_text = f"{baseline_rssi:.1f} dBm"
            baseline_amp_text = f"{baseline_amp:.1f}"

        presence_text = f"{presence:.1f}"
        raw_presence = item.get("raw_presence", 0.0)
        presence_baseline = item.get("presence_baseline")
        calibration_kind = item.get("calibration_kind")
        calibration_progress = item.get("calibration_progress", 0.0)
        noise_floor = item.get("noise_floor", 0.0)
        smoothing = item.get("smoothing", 0.0)
        motion_weight = item.get("motion_weight", 0.0)
        rssi_delta = item.get("rssi_delta", 0.0)
        amp_delta = item.get("amp_delta", 0.0)
        motion_score = item.get("motion_score", 0.0)
        rssi_motion = item.get("rssi_motion", 0.0)
        amp_motion = item.get("amp_motion", 0.0)

        painter.setFont(QtGui.QFont("Menlo", 12))
        painter.setPen(QtGui.QColor(0, 0, 0))
        painter.drawText(rect.adjusted(16, 74, -16, 0), QtCore.Qt.AlignLeft, f"RSSI    {rssi_text}")
        painter.drawText(rect.adjusted(16, 92, -16, 0), QtCore.Qt.AlignLeft, f"amp      {amp_text}")
        painter.drawText(rect.adjusted(16, 110, -16, 0), QtCore.Qt.AlignLeft, f"base    {baseline_rssi_text} / {baseline_amp_text}")
        painter.drawText(rect.adjusted(16, 128, -16, 0), QtCore.Qt.AlignLeft, f"static  {rssi_delta:.1f} / {amp_delta:.1f}")
        painter.drawText(rect.adjusted(16, 146, -16, 0), QtCore.Qt.AlignLeft, f"motion  {rssi_motion:.1f} / {amp_motion:.1f}")

        painter.setPen(QtGui.QColor(190, 35, 28) if blocked else QtGui.QColor(0, 0, 0))
        painter.setFont(QtGui.QFont("Menlo", 13, QtGui.QFont.Bold))
        painter.drawText(rect.adjusted(16, 164, -16, 0), QtCore.Qt.AlignLeft, f"score {presence_text}  mv {motion_score:.1f}")

        painter.setPen(QtGui.QColor(95, 95, 95))
        painter.setFont(QtGui.QFont("Menlo", 10))
        painter.drawText(
            rect.adjusted(16, 184, -16, 0),
            QtCore.Qt.AlignLeft,
            f"raw {raw_presence:.1f} floor {noise_floor:.1f} sm {smoothing:.2f} mw {motion_weight:.2f}",
        )
        present_text = "--" if presence_baseline is None else f"{presence_baseline:.1f}"
        if calibration_kind:
            present_text = f"{calibration_kind} {calibration_progress * 100:.0f}%"
        painter.drawText(rect.adjusted(16, 200, -16, 0), QtCore.Qt.AlignLeft, f"present base {present_text}")

    def _draw_indicator(self, painter):
        cy = min(410, self.height() - 300)
        radius = 58
        gap = 24
        indicator_width = 3 * (radius * 2) + 2 * gap
        start_x = (self.width() - indicator_width) / 2.0

        for idx, zone in enumerate(ZONE_ORDER):
            item = self.state.get(zone, self._empty_state())
            ready = self._zone_ready(item)
            blocked = self._is_blocked(zone, item)

            cx = start_x + radius + idx * (radius * 2 + gap)

            if not item.get("connected"):
                color = QtGui.QColor(235, 235, 230)
                label = "not connected"
            elif not item.get("valid_signal", True):
                color = QtGui.QColor(170, 170, 170)
                label = "weak RSSI"
            elif not ready:
                color = QtGui.QColor(215, 215, 210)
                label = "calibrating"
            elif blocked:
                color = QtGui.QColor(210, 35, 28)
                label = "blocked"
            else:
                color = QtGui.QColor(40, 150, 82)
                label = "clear"

            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QtCore.QPointF(cx, cy), radius, radius)

            painter.setPen(QtGui.QColor(0, 0, 0))
            painter.setFont(QtGui.QFont("Helvetica Neue", 14, QtGui.QFont.Medium))
            painter.drawText(QtCore.QRectF(cx - radius, cy - 10, radius * 2, 20), QtCore.Qt.AlignCenter, zone.upper())

            painter.setFont(QtGui.QFont("Helvetica Neue", 12))
            painter.setPen(QtGui.QColor(120, 120, 120))
            painter.drawText(QtCore.QRectF(cx - radius, cy + radius + 4, radius * 2, 18), QtCore.Qt.AlignCenter, label)


def parse_receivers(items):
    receivers = dict(DEFAULT_RECEIVERS)
    for item in items or []:
        label, port = item.split("=", 1)
        if label not in ZONE_ORDER:
            raise ValueError(f"unknown receiver label: {label}")
        if port.strip().lower() in ("", "none", "off", "disabled", "skip"):
            receivers.pop(label, None)
        else:
            receivers[label] = port
    return receivers


def main():
    parser = argparse.ArgumentParser(description="CSI presence detection using amplitude + RSSI.")
    parser.add_argument("--receiver", action="append", help="Receiver mapping, e.g. center=/dev/cu.usbmodem1101")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--baseline-frames", type=int, default=250)
    parser.add_argument("--threshold", type=float, default=2.5)
    parser.add_argument("--emit-interval", type=float, default=0.06)
    parser.add_argument("--min-rssi", type=int, default=DEFAULT_MIN_RSSI)
    parser.add_argument("--window-size", type=int, default=64)
    parser.add_argument("--average-size", type=int, default=16)
    parser.add_argument("--integrator", type=int, default=3)
    parser.add_argument("--model", help="Optional zone_model.json from csi_labeled_accuracy_test.py")
    parser.add_argument("--model-window", type=int, default=90)
    parser.add_argument("--sse-port", type=int, help="Stream confidence JSON for JavaScript over Server-Sent Events.")
    parser.add_argument("--output-enter", type=float, default=0.42, help="Output confidence needed to enter presence.")
    parser.add_argument("--output-exit", type=float, default=0.28, help="Output confidence below which presence is released.")
    parser.add_argument("--output-gap", type=float, default=0.10, help="Minimum top-vs-second channel gap unless signal is strong.")
    parser.add_argument("--output-strong", type=float, default=0.65, help="Allow multi-channel output above this confidence even with a small gap.")
    parser.add_argument("--output-attack", type=float, default=0.22, help="Output smoothing speed when confidence rises.")
    parser.add_argument("--output-release", type=float, default=0.07, help="Output smoothing speed when confidence falls.")
    args = parser.parse_args()

    app = QtWidgets.QApplication(sys.argv)
    view = PresenceView(args.threshold, args.baseline_frames)
    sse_server = None
    if args.sse_port:
        sse_server = SseOutputServer(args.sse_port)
        sse_server.start()
        print(f"SSE output active: http://127.0.0.1:{args.sse_port}/events", flush=True)
    stabilizer = OutputStabilizer(
        enter_threshold=args.output_enter,
        exit_threshold=args.output_exit,
        min_gap=args.output_gap,
        strong_threshold=args.output_strong,
        attack=args.output_attack,
        release=args.output_release,
    )
    output = JsonOutput(
        view.get_thresholds,
        lambda: view.flip_output,
        stabilizer,
        sse_server,
        view.get_active_channels,
        view.get_thresholds,
        view.get_release_ratios,
    )
    app.output = output
    app.sse_server = sse_server
    worker = SerialWorker(
        parse_receivers(args.receiver),
        args.baud,
        args.baseline_frames,
        args.emit_interval,
        args.min_rssi,
        args.window_size,
        args.average_size,
        args.integrator,
        args.model,
        args.model_window,
    )
    worker.values.connect(view.set_values)
    worker.values.connect(output.send_state)
    worker.status.connect(view.set_status)
    worker.status.connect(lambda msg: print(msg, flush=True))
    view.recalibrate_requested.connect(worker.recalibrate_requested)
    view.zone_calibration_requested.connect(worker.zone_calibration_requested)
    view.tuning_changed.connect(worker.tuning_changed)
    app.aboutToQuit.connect(worker.stop)
    if sse_server:
        app.aboutToQuit.connect(sse_server.stop)

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
