#!/usr/bin/env python3

import argparse
import csv
import json
import statistics as stats
from pathlib import Path


def percentile(values, q):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * q)))
    return ordered[index]


def load_amp_delta_columns(path, sample_limit):
    with Path(path).open() as handle:
        reader = csv.DictReader(handle)
        columns = [name for name in reader.fieldnames or [] if name.startswith("amp_delta_")]
        values = {name: [] for name in columns}
        rows = 0
        for row in reader:
            rows += 1
            for name in columns:
                raw = row.get(name)
                if raw in (None, ""):
                    continue
                try:
                    values[name].append(float(raw))
                except ValueError:
                    pass
            if sample_limit and rows >= sample_limit:
                break
    return values, rows


def analyze(path, args):
    values, rows = load_amp_delta_columns(path, args.sample_limit)
    metrics = []
    for index, name in enumerate(sorted(values)):
        data = values[name]
        if len(data) < args.min_samples:
            metrics.append(
                {
                    "index": index,
                    "samples": len(data),
                    "usable": False,
                    "reason": "too_few_samples",
                }
            )
            continue

        mean = stats.mean(data)
        stdev = stats.pstdev(data)
        p50 = percentile(data, 0.50)
        p95 = percentile(data, 0.95)
        max_value = max(data)
        cv = stdev / mean if mean > 1e-9 else 0.0
        dynamic = p95 - p50

        reason = "usable"
        usable = True
        if max_value < args.min_max:
            usable = False
            reason = "dead_or_flat"
        elif mean < args.min_mean:
            usable = False
            reason = "low_signal"
        elif dynamic < args.min_dynamic:
            usable = False
            reason = "low_dynamic_range"
        elif cv > args.max_cv:
            usable = False
            reason = "unstable_noise"

        metrics.append(
            {
                "index": index,
                "samples": len(data),
                "mean": mean,
                "stdev": stdev,
                "cv": cv,
                "p50": p50,
                "p95": p95,
                "max": max_value,
                "dynamic": dynamic,
                "usable": usable,
                "reason": reason,
            }
        )

    usable_indices = [item["index"] for item in metrics if item.get("usable")]
    rejected = {}
    for item in metrics:
        if item.get("usable"):
            continue
        rejected[item["reason"]] = rejected.get(item["reason"], 0) + 1

    return {
        "source": str(path),
        "rows_scanned": rows,
        "subcarriers": len(metrics),
        "usable_count": len(usable_indices),
        "rejected_count": len(metrics) - len(usable_indices),
        "usable_indices": usable_indices,
        "rejected_by_reason": rejected,
        "thresholds": {
            "min_samples": args.min_samples,
            "min_mean": args.min_mean,
            "min_max": args.min_max,
            "min_dynamic": args.min_dynamic,
            "max_cv": args.max_cv,
        },
        "metrics": metrics,
    }


def main():
    parser = argparse.ArgumentParser(description="Analyze CSI amp_delta subcarrier quality from feature CSV.")
    parser.add_argument("csv_path")
    parser.add_argument("--out", default="captures/subcarrier_quality.json")
    parser.add_argument("--sample-limit", type=int, default=0)
    parser.add_argument("--min-samples", type=int, default=80)
    parser.add_argument("--min-mean", type=float, default=0.02)
    parser.add_argument("--min-max", type=float, default=0.25)
    parser.add_argument("--min-dynamic", type=float, default=0.08)
    parser.add_argument("--max-cv", type=float, default=6.0)
    args = parser.parse_args()

    result = analyze(args.csv_path, args)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n")

    print(json.dumps({k: result[k] for k in (
        "source",
        "rows_scanned",
        "subcarriers",
        "usable_count",
        "rejected_count",
        "rejected_by_reason",
    )}, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
