#!/usr/bin/env python3
"""
Ghép nhiều cảnh: nối các video whiteboard MP4 của từng cảnh theo thứ tự (cắt cứng) thành một video hoàn chỉnh.

Ưu tiên dùng ffmpeg của hệ thống để nối không suy hao (-c copy, không mã hóa lại). Nếu các đoạn khác kích thước/codec
hoặc không có ffmpeg thì chuyển sang PyAV mã hóa lại từng khung hình, co giãn và thêm viền cho khớp kích thước đoạn đầu. Các đoạn gốc vẫn được giữ nguyên.

Cách dùng:
  <ENV_PY> merge_scenes.py --inputs a.mp4 b.mp4 c.mp4 --output final.mp4
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _ffmpeg_concat_copy(inputs: list[Path], output: Path) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return False
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        for p in inputs:
            f.write(f"file '{p.resolve().as_posix()}'\n")
        list_path = Path(f.name)
    try:
        res = subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", str(list_path), "-c", "copy", str(output)],
            capture_output=True, text=True,
        )
        if res.returncode == 0:
            print(f"  ffmpeg nối không suy hao xong: {output}")
            return True
        print(f"  [warn] ffmpeg -c copy thất bại, thử mã hóa lại: {res.stderr.strip()[:200]}")
        res = subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", str(list_path), "-c:v", "libx264", "-crf", "20",
             "-pix_fmt", "yuv420p", "-vf", "scale='trunc(iw/2)*2':'trunc(ih/2)*2'", str(output)],
            capture_output=True, text=True,
        )
        if res.returncode == 0:
            print(f"  ffmpeg nối bằng mã hóa lại xong: {output}")
            return True
        print(f"  [warn] ffmpeg mã hóa lại cũng thất bại: {res.stderr.strip()[:200]}")
        return False
    finally:
        list_path.unlink(missing_ok=True)


def _pyav_concat(inputs: list[Path], output: Path) -> bool:
    try:
        import av
    except ImportError:
        return False
    import numpy as np  # noqa: F401
    first = av.open(str(inputs[0]))
    vs = first.streams.video[0]
    w, h = vs.codec_context.width, vs.codec_context.height
    rate = vs.average_rate
    first.close()

    out = av.open(str(output), mode="w")
    ostream = out.add_stream("h264", rate=rate)
    ostream.width, ostream.height = w, h
    ostream.pix_fmt = "yuv420p"
    ostream.options = {"crf": "24", "preset": "medium"}
    for p in inputs:
        cont = av.open(str(p))
        for frame in cont.decode(video=0):
            if frame.width != w or frame.height != h:
                frame = frame.reformat(width=w, height=h)
            for pkt in ostream.encode(frame):
                out.mux(pkt)
        cont.close()
    for pkt in ostream.encode(None):
        out.mux(pkt)
    out.close()
    print(f"  PyAV nối xong: {output}")
    return True


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Ghép nhiều cảnh whiteboard MP4 theo thứ tự")
    p.add_argument("--inputs", nargs="+", required=True, help="Danh sách MP4 theo thứ tự phát")
    p.add_argument("--output", required=True, help="Đường dẫn file xuất sau khi ghép")
    args = p.parse_args(argv)

    inputs = [Path(x) for x in args.inputs]
    missing = [str(x) for x in inputs if not x.exists()]
    if missing:
        print(f"[err] Thiếu file đầu vào: {', '.join(missing)}", file=sys.stderr)
        return 1
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    if _ffmpeg_concat_copy(inputs, output) or _pyav_concat(inputs, output):
        print(f"OUTPUT={output.resolve()}")
        return 0
    print("[err] Ghép thất bại: hệ thống không có ffmpeg và PyAV không dùng được", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
