#!/usr/bin/env python3
"""Main entry for the RIYIO pipeline.

Usage:
  python pipeline.py ensure-queue
  python pipeline.py next
  python pipeline.py produce --song S --clips DIR --out OUT.mp4
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pipeline_lib.queue_manager import ensure_queue, next_ready, mark_done
from pipeline_lib.qc import qc_video
from pipeline_lib.uploader import upload_dual


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ensure-queue")
    sub.add_parser("next")
    p = sub.add_parser("produce")
    p.add_argument("--song", type=Path)
    p.add_argument("--clips", type=Path)
    p.add_argument("--out", type=Path, default=Path("out.mp4"))
    p.add_argument("--title", default="RIYIO Edit")
    a = ap.parse_args(argv)

    if a.cmd == "ensure-queue":
        ensure_queue()
        print("queue ensured")
    elif a.cmd == "next":
        item = next_ready()
        print(item or "empty")
    elif a.cmd == "produce":
        if not a.song or not a.clips:
            print("need --song and --clips", file=sys.stderr)
            sys.exit(1)
        import subprocess
        cmd = [sys.executable, "vicestyle.py", "auto",
               "--song", str(a.song), "--clips", str(a.clips),
               "--out", str(a.out), "--mode", "dual"]
        subprocess.check_call(cmd)
        wide = a.out.with_suffix(".wide.mp4")
        shorts = a.out.with_suffix(".shorts.mp4")
        ok, reasons = qc_video(wide)
        print("QC:", ok, reasons)
        if ok:
            upload_dual(wide, shorts, a.title)
        mark_done(a.out.stem)


if __name__ == "__main__":
    main()
