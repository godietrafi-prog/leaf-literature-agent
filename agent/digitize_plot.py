#!/usr/bin/env python3
"""Convert manually or automatically traced plot pixels into staged data rows.

Calibration JSON example:
{
  "x": {"pixel1": 120, "value1": 0, "pixel2": 920, "value2": 10, "scale": "linear"},
  "y": {"pixel1": 700, "value1": 0, "pixel2": 100, "value2": 100, "scale": "linear"}
}

Input point CSV requires pixel_x,pixel_y and may include series/condition columns.
The output is always unapproved graph_digitized evidence.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

from PIL import Image


def axis_value(pixel: float, axis: dict) -> float:
    p1, p2 = float(axis["pixel1"]), float(axis["pixel2"])
    v1, v2 = float(axis["value1"]), float(axis["value2"])
    if p1 == p2:
        raise ValueError("calibration pixels must differ")
    fraction = (pixel - p1) / (p2 - p1)
    scale = axis.get("scale", "linear")
    if scale == "linear":
        return v1 + fraction * (v2 - v1)
    if scale == "log10":
        if v1 <= 0 or v2 <= 0:
            raise ValueError("log10 calibration values must be positive")
        return 10 ** (math.log10(v1) + fraction * (math.log10(v2) - math.log10(v1)))
    raise ValueError(f"unsupported axis scale {scale!r}")


def color_points(image_path: Path, rgb: tuple[int, int, int], tolerance: int,
                 x_min: int, x_max: int, y_min: int, y_max: int, bin_width: int) -> list[dict]:
    image = Image.open(image_path).convert("RGB")
    pixels = image.load()
    buckets: dict[int, list[tuple[int, int]]] = {}
    for x in range(max(0, x_min), min(image.width, x_max + 1)):
        for y in range(max(0, y_min), min(image.height, y_max + 1)):
            value = pixels[x, y]
            if max(abs(value[i] - rgb[i]) for i in range(3)) <= tolerance:
                buckets.setdefault((x - x_min) // bin_width, []).append((x, y))
    points = []
    for bucket in sorted(buckets):
        values = buckets[bucket]
        if len(values) < 2:
            continue
        # Median-like centre is robust to line thickness.
        xs = sorted(x for x, _ in values)
        ys = sorted(y for _, y in values)
        points.append({"pixel_x": xs[len(xs) // 2], "pixel_y": ys[len(ys) // 2],
                       "series": f"rgb{rgb}"})
    return points


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--figure-label", required=True)
    parser.add_argument("--pdf-page", type=int, required=True)
    parser.add_argument("--quantity", required=True)
    parser.add_argument("--unit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--estimated-error", type=float, required=True)
    parser.add_argument("--points", type=Path, help="CSV with pixel_x,pixel_y")
    parser.add_argument("--trace-rgb", help="automatic trace target as R,G,B")
    parser.add_argument("--tolerance", type=int, default=25)
    parser.add_argument("--bounds", help="x_min,x_max,y_min,y_max for colour tracing")
    parser.add_argument("--bin-width", type=int, default=4)
    args = parser.parse_args()
    calibration = json.loads(args.calibration.read_text(encoding="utf-8"))
    if args.points:
        with args.points.open(encoding="utf-8", newline="") as handle:
            points = list(csv.DictReader(handle))
        mode = "manual_pixels"
    elif args.trace_rgb and args.bounds:
        rgb = tuple(map(int, args.trace_rgb.split(",")))
        bounds = tuple(map(int, args.bounds.split(",")))
        if len(rgb) != 3 or len(bounds) != 4:
            raise SystemExit("--trace-rgb requires 3 and --bounds requires 4 comma-separated integers")
        points = color_points(args.image, rgb, args.tolerance, *bounds, args.bin_width)
        mode = "colour_autotrace"
    else:
        raise SystemExit("provide --points or both --trace-rgb and --bounds")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for index, point in enumerate(points, start=1):
            x_value = axis_value(float(point["pixel_x"]), calibration["x"])
            y_value = axis_value(float(point["pixel_y"]), calibration["y"])
            raw = f"{args.paper_id}|{args.figure_label}|{index}|{x_value}|{y_value}"
            row = {
                "proposal_id": hashlib.sha1(raw.encode()).hexdigest()[:14],
                "paper_id": args.paper_id, "quantity": args.quantity, "value": y_value,
                "unit": args.unit, "sd_error": None, "error_type": None,
                "n_replicates": None, "p_value": None, "method": None, "species": None,
                "treatment_condition": point.get("condition") or f"x={x_value:g}", "basis": None,
                "source_location": f"Figure {args.figure_label}, PDF page {args.pdf_page}; digitized point {index}",
                "is_from_SI": 0, "extraction_mode": "graph_digitized",
                "figure_label": args.figure_label, "digitization_resolution": str(args.image),
                "estimated_error": args.estimated_error, "trace_mode": mode,
                "pixel_x": float(point["pixel_x"]), "pixel_y": float(point["pixel_y"]),
                "x_value": x_value, "status": "needs_review", "needs_human": 1,
                "review_note": "Confirm calibration, series identity, axes and digitized point",
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Wrote {len(points)} unapproved digitized points to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
