#!/usr/bin/env python3

import argparse
import ast
import csv
import json
import math
import statistics as stats
import threading
import time
from collections import defaultdict
from pathlib import Path


DEFAULT_RECEIVERS = {
    "left": "/dev/cu.usbmodem101",
    "center": "/dev/cu.usbmodem1101",
    "right": "/dev/cu.usbmodem2101",
}

DEFAULT_PHASES = ("baseline", "left", "center", "right")


def median(values, default=0.0):
    if not values:
        return default
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def percentile(values, pct, default=0.0):
    if not values:
        return default
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * pct)))
    return ordered[idx]


def mad(values, center):
    return median([abs(value - center) for value in values], default=0.0)


def parse_csi(line):
    start = line.find("CSI_DATA")
    if start < 0:
        return None
    try:
        row = next(csv.reader([line[start:].strip()]))
        values = ast.literal_eval(row[-1])
        amps = []
        phases = []
        for i in range(0, len(values) - 1, 2):
            imag = values[i]
            real = values[i + 1]
            amps.append(math.hypot(real, imag))
            phases.append(math.atan2(imag, real))
        if not amps:
            return None
        return {
            "rssi": int(row[3]),
            "timestamp": int(row[18]),
            "channel": int(row[16]),
            "amps": amps,
            "phases": phases,
        }
    except Exception:
        return None


def load_frames(path):
    frames = []
    if not path.exists():
        return frames
    for line in path.read_text(errors="replace").splitlines():
        parsed = parse_csi(line)
        if parsed:
            frames.append(parsed)
    return frames


def receiver_mapping(items):
    receivers = dict(DEFAULT_RECEIVERS)
    for item in items or []:
        label, port = item.split("=", 1)
        receivers[label] = port
    return receivers


def capture_port(label, port, baud, duration, output_path, result):
    import serial

    started = time.monotonic()
    lines = []
    valid = 0
    try:
        with serial.Serial(port, baud, timeout=0.03) as stream:
            while time.monotonic() - started < duration:
                line = stream.readline().decode("utf-8", "replace").strip()
                if not line:
                    continue
                lines.append(line)
                if parse_csi(line):
                    valid += 1
        output_path.write_text("\n".join(lines) + "\n")
        result[label] = {"ok": True, "lines": len(lines), "valid": valid}
    except Exception as exc:
        result[label] = {"ok": False, "error": str(exc), "lines": len(lines), "valid": valid}


def capture_phase(phase, receivers, baud, duration, outdir):
    result = {}
    threads = []
    for label, port in receivers.items():
        output_path = outdir / f"{phase}_{label}.csv"
        thread = threading.Thread(
            target=capture_port,
            args=(label, port, baud, duration, output_path, result),
            daemon=True,
        )
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join()
    (outdir / f"{phase}_summary.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def run_capture(args):
    receivers = receiver_mapping(args.receiver)
    phases = args.phase or list(DEFAULT_PHASES)
    outdir = Path(args.outdir) / time.strftime("accuracy_%Y%m%d_%H%M%S")
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "receivers.json").write_text(json.dumps(receivers, indent=2) + "\n")

    print(f"output: {outdir}", flush=True)
    for phase in phases:
        print("", flush=True)
        print(f"NEXT: {phase.upper()}", flush=True)
        if phase == "baseline":
            print("Leave the sensing area empty.", flush=True)
        else:
            print(f"Stand still in the marked {phase.upper()} zone.", flush=True)
        for remaining in range(args.delay, 0, -1):
            print(f"starting {phase} in {remaining}s", flush=True)
            time.sleep(1)
        print(f"recording {phase} for {args.duration}s", flush=True)
        result = capture_phase(phase, receivers, args.baud, args.duration, outdir)
        print(json.dumps(result, indent=2), flush=True)

    analyze_outdir(outdir, phases, receivers.keys())
    print(f"report: {outdir / 'analysis_report.md'}", flush=True)


def baseline_model(frames):
    width = min((len(frame["amps"]) for frame in frames), default=0)
    if width == 0:
        return {"median": [], "scale": [], "mask": [], "rssi_median": 0.0, "rssi_scale": 1.0}

    med = []
    scale = []
    for i in range(width):
        column = [frame["amps"][i] for frame in frames]
        c = median(column)
        s = max(mad(column, c) * 1.4826, c * 0.012, 1.0)
        med.append(c)
        scale.append(s)

    # Keep stable, non-flat carriers. This removes padding/null carriers and noisy tails.
    scored = []
    for i, (c, s) in enumerate(zip(med, scale)):
        if c <= 2.0:
            continue
        cv = s / max(c, 1.0)
        scored.append((cv, i))
    scored.sort()
    keep_count = min(96, max(24, int(len(scored) * 0.65))) if scored else 0
    mask = [i for _, i in scored[:keep_count]]

    rssi_values = [frame["rssi"] for frame in frames]
    rssi_median = median(rssi_values)
    rssi_scale = max(mad(rssi_values, rssi_median) * 1.4826, 1.0)
    return {
        "median": med,
        "scale": scale,
        "mask": mask,
        "rssi_median": rssi_median,
        "rssi_scale": rssi_scale,
    }


def frame_features(frame, model, prev_frame):
    amps = frame["amps"]
    width = min(len(amps), len(model["median"]), len(model["scale"]))
    indices = [i for i in model["mask"] if i < width]
    if not indices:
        indices = list(range(width))

    z = [
        abs(amps[i] - model["median"][i]) / max(model["scale"][i], 1.0)
        for i in indices
    ]
    top_k = max(1, int(len(z) * 0.15))
    top_z = sorted(z)[-top_k:]

    motion = 0.0
    if prev_frame:
        prev = prev_frame["amps"]
        motion_vals = [
            abs(amps[i] - prev[i]) / max(model["scale"][i], 1.0)
            for i in indices
            if i < len(prev)
        ]
        if motion_vals:
            motion = median(sorted(motion_vals)[-top_k:])

    rssi_drop = max(0.0, model["rssi_median"] - frame["rssi"]) / max(model["rssi_scale"], 1.0)
    return {
        "top_amp_z": median(top_z),
        "mean_amp_z": sum(z) / len(z) if z else 0.0,
        "motion_z": motion,
        "rssi_drop_z": rssi_drop,
    }


def phase_receiver_features(frames, model):
    values = defaultdict(list)
    prev = None
    for frame in frames:
        feats = frame_features(frame, model, prev)
        prev = frame
        for key, value in feats.items():
            values[key].append(value)
    return {
        key: {
            "median": median(vals),
            "p75": percentile(vals, 0.75),
            "p95": percentile(vals, 0.95),
        }
        for key, vals in values.items()
    }


def score_features(features):
    if not features:
        return 0.0
    top_amp = features.get("top_amp_z", {}).get("median", 0.0)
    motion = features.get("motion_z", {}).get("p75", 0.0)
    rssi = features.get("rssi_drop_z", {}).get("median", 0.0)
    return 0.58 * top_amp + 0.27 * motion + 0.15 * rssi


def analyze_outdir(outdir, phases, receiver_labels):
    outdir = Path(outdir)
    phases = list(phases)
    receiver_labels = list(receiver_labels)
    baseline_phase = "baseline"

    baseline = {}
    for label in receiver_labels:
        baseline[label] = baseline_model(load_frames(outdir / f"{baseline_phase}_{label}.csv"))

    report = {
        "outdir": str(outdir),
        "receivers": {},
        "phases": {},
        "confusion": {},
    }
    lines = ["# CSI Accuracy Test Report", ""]

    for label in receiver_labels:
        frames = load_frames(outdir / f"{baseline_phase}_{label}.csv")
        model = baseline[label]
        report["receivers"][label] = {
            "baseline_rows": len(frames),
            "usable_subcarriers": len(model["mask"]),
            "baseline_rssi": model["rssi_median"],
            "baseline_rssi_scale": model["rssi_scale"],
        }
    lines.append("## Receiver Baselines")
    for label, info in report["receivers"].items():
        lines.append(
            f"- {label}: {info['baseline_rows']} rows, {info['usable_subcarriers']} usable subcarriers, "
            f"RSSI {info['baseline_rssi']:.1f} dBm"
        )

    for phase in phases:
        phase_info = {}
        scores = {}
        for label in receiver_labels:
            frames = load_frames(outdir / f"{phase}_{label}.csv")
            features = phase_receiver_features(frames, baseline[label])
            score = score_features(features)
            phase_info[label] = {"rows": len(frames), "features": features, "score": score}
            scores[label] = score
        total = sum(max(v, 0.0) for v in scores.values()) or 1.0
        confidence = {label: max(score, 0.0) / total for label, score in scores.items()}
        winner = max(confidence, key=confidence.get)
        phase_info["winner"] = winner
        phase_info["confidence"] = confidence
        report["phases"][phase] = phase_info

    lines.extend(["", "## Phase Scores"])
    for phase in phases:
        info = report["phases"][phase]
        conf = info["confidence"]
        lines.append(f"- {phase}: winner={info['winner']}, confidence " + ", ".join(
            f"{label}={conf[label]:.2f}" for label in receiver_labels
        ))
        for label in receiver_labels:
            entry = info[label]
            feat = entry["features"]
            top = feat.get("top_amp_z", {}).get("median", 0.0)
            mot = feat.get("motion_z", {}).get("p75", 0.0)
            rssi = feat.get("rssi_drop_z", {}).get("median", 0.0)
            lines.append(f"  - {label}: rows={entry['rows']}, score={entry['score']:.2f}, amp={top:.2f}, motion={mot:.2f}, rssi={rssi:.2f}")

    lines.extend(["", "## Suggested Processing"])
    lines.append("- Use per-receiver baseline median/MAD normalization, not raw RSSI or raw amplitude.")
    lines.append("- Ignore subcarriers outside each receiver's stable baseline mask.")
    lines.append("- For presence, start with `0.58 * top_amp_z + 0.27 * motion_z + 0.15 * rssi_drop_z`.")
    lines.append("- For position, normalize the three receiver scores into confidence values and use the highest confidence only if it beats the next receiver by a visible margin.")

    (outdir / "analysis.json").write_text(json.dumps(report, indent=2) + "\n")
    (outdir / "analysis_report.md").write_text("\n".join(lines) + "\n")
    write_zone_model(outdir, phases, receiver_labels, baseline)
    print("\n".join(lines), flush=True)


def signed_response_vector(frames_by_receiver, baseline, receiver_labels):
    vector = []
    for label in receiver_labels:
        frames = frames_by_receiver.get(label, [])
        model = baseline[label]
        if not frames:
            vector.extend([0.0] * 8)
            continue

        width = min(
            [len(model["median"]), len(model["scale"])]
            + [len(frame["amps"]) for frame in frames]
        )
        values = []
        for i in range(width):
            if model["median"][i] <= 2.0:
                continue
            column = [
                (frame["amps"][i] - model["median"][i]) / max(model["scale"][i], 1.0)
                for frame in frames
            ]
            values.append(median(column))

        ordered = sorted(values)
        if ordered:
            for pct in (0.05, 0.15, 0.30, 0.50, 0.70, 0.85, 0.95):
                vector.append(percentile(ordered, pct))
        else:
            vector.extend([0.0] * 7)

        rssi_values = [frame["rssi"] for frame in frames]
        vector.append(model["rssi_median"] - median(rssi_values))
    return vector


def write_zone_model(outdir, phases, receiver_labels, baseline):
    outdir = Path(outdir)
    receiver_labels = list(receiver_labels)
    templates = {}
    for phase in phases:
        frames_by_receiver = {
            label: load_frames(outdir / f"{phase}_{label}.csv")
            for label in receiver_labels
        }
        templates[phase] = signed_response_vector(frames_by_receiver, baseline, receiver_labels)

    model = {
        "version": 1,
        "description": "Signed normalized CSI response quantile templates.",
        "receivers": receiver_labels,
        "features_per_receiver": ["q05", "q15", "q30", "q50", "q70", "q85", "q95", "rssi_drop"],
        "baseline": {
            label: {
                "median": baseline[label]["median"],
                "scale": baseline[label]["scale"],
                "rssi_median": baseline[label]["rssi_median"],
            }
            for label in receiver_labels
        },
        "templates": templates,
    }
    (outdir / "zone_model.json").write_text(json.dumps(model, indent=2) + "\n")


def run_analyze(args):
    outdir = Path(args.outdir)
    receivers = receiver_mapping(args.receiver)
    phases = args.phase or list(DEFAULT_PHASES)
    analyze_outdir(outdir, phases, receivers.keys())


def main():
    parser = argparse.ArgumentParser(description="Capture and analyze labeled CSI receiver data.")
    sub = parser.add_subparsers(dest="command", required=True)

    capture = sub.add_parser("capture")
    capture.add_argument("--receiver", action="append")
    capture.add_argument("--baud", type=int, default=921600)
    capture.add_argument("--duration", type=int, default=12)
    capture.add_argument("--delay", type=int, default=6)
    capture.add_argument("--phase", action="append")
    capture.add_argument("--outdir", default="captures")
    capture.set_defaults(func=run_capture)

    analyze = sub.add_parser("analyze")
    analyze.add_argument("--receiver", action="append")
    analyze.add_argument("--phase", action="append")
    analyze.add_argument("--outdir", required=True)
    analyze.set_defaults(func=run_analyze)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
