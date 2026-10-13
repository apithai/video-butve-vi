#!/usr/bin/env python3
"""
Hoạt ảnh nét bút chảy - script chuẩn bị môi trường

Nhiệm vụ:
  1. Tạo môi trường ảo Python tách biệt trong thư mục skill (đã có thì dùng lại)
  2. Kiểm tra các thư viện bên thứ ba cần thiết có import được không
  3. Tự động cài bổ sung thư viện còn thiếu
  4. In dòng cuối ENV_PY=<đường dẫn trình thông dịch> để bên gọi bắt lấy

Cách dùng:
  python prepare_env.py          # tạo môi trường + cài thư viện thiếu, xuất ENV_PY
  python prepare_env.py --check  # chỉ dò kiểm, thiếu gì thì thoát với mã khác 0
"""
from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

# Thư mục gốc của skill = lên hai cấp từ script này
SKILL_ROOT = Path(__file__).resolve().parent.parent
VENV_ROOT = SKILL_ROOT / ".venv"

# Tên import -> tên cài bằng pip
DEPS: dict[str, str] = {
    "cv2": "opencv-python",
    "numpy": "numpy",
    "av": "av",  # PyAV: mã hóa H.264 cài thuần bằng pip, không cần ffmpeg của hệ thống
    "PIL": "Pillow",  # render_annotation_preview.py vẽ ảnh xem trước đánh số vùng (có nhãn)
}


def interpreter_path() -> Path:
    """Vị trí file thực thi python trong môi trường ảo (đa nền tảng)."""
    if sys.platform.startswith("win"):
        return VENV_ROOT / "Scripts" / "python.exe"
    return VENV_ROOT / "bin" / "python"


def ensure_venv(check_only: bool) -> Path:
    py = interpreter_path()
    if VENV_ROOT.exists() and py.exists():
        print(f"[ok] Dùng lại môi trường ảo hiện có: {VENV_ROOT}")
        return py

    if check_only:
        print(f"[err] Chưa tạo môi trường ảo: {VENV_ROOT}")
        sys.exit(1)

    print(f"[..] Đang tạo môi trường ảo: {VENV_ROOT}")
    venv.create(str(VENV_ROOT), with_pip=True)
    print("[ok] Môi trường ảo đã sẵn sàng")
    return py


def can_import(py: Path, import_name: str) -> bool:
    probe = subprocess.run(
        [str(py), "-c", f"import {import_name}"],
        capture_output=True,
    )
    return probe.returncode == 0


def install(py: Path, packages: list[str]) -> bool:
    if not packages:
        return True
    print(f"[..] Đang cài thư viện: {', '.join(packages)}")
    res = subprocess.run(
        [str(py), "-m", "pip", "install", "--quiet", *packages],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        print(f"[err] Cài đặt thất bại:\n{res.stderr}")
        return False
    print("[ok] Cài thư viện xong")
    return True


def main() -> None:
    check_only = "--check" in sys.argv

    py = ensure_venv(check_only)

    missing: list[str] = []
    for import_name, pip_name in DEPS.items():
        if can_import(py, import_name):
            print(f"[ok] {pip_name}")
        else:
            print(f"[miss] {pip_name}")
            missing.append(pip_name)

    if missing:
        if check_only:
            print(f"\nThiếu {len(missing)} thư viện: {', '.join(missing)}")
            sys.exit(1)
        if not install(py, missing):
            sys.exit(1)

    # Dòng cuối: kết quả quy ước để bên gọi bắt lấy
    print(f"\nENV_PY={py}")


if __name__ == "__main__":
    main()
