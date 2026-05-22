#!/usr/bin/env python3
"""WormTracker 跨平台打包脚本

在 macOS 或 Windows 上运行此脚本，自动调用 PyInstaller 生成可执行文件。

- Windows: 生成 dist/WormTracker.exe (单文件)
- macOS:   生成 dist/WormTracker.app (应用包)

用法:
    python build.py              # 打包
    python build.py --clean      # 清理后重新打包
    python build.py --zip        # 打包后额外生成 zip 压缩包便于分发
"""

import os
import sys
import shutil
import subprocess
import argparse
import platform
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
SPEC_FILE = ROOT / "wormtracker.spec"
NAME = "WormTracker"


def check_pyinstaller() -> bool:
    """检查 PyInstaller 是否可用"""
    try:
        import PyInstaller
        return True
    except ImportError:
        return False


def clean_build():
    """清理旧的构建产物"""
    for d in [DIST, BUILD]:
        if d.exists():
            print(f"🧹 清理 {d}")
            shutil.rmtree(d)
    # 清理临时文件
    for p in ROOT.glob("*.pyc"):
        p.unlink()
    for p in ROOT.glob("__pycache__"):
        if p.is_dir():
            shutil.rmtree(p)


def get_output_name() -> str:
    """生成输出包名"""
    plat = platform.system()  # Darwin / Windows
    arch = platform.machine()
    date_str = datetime.now().strftime("%Y%m%d")
    return f"{NAME}-{plat}-{arch}-{date_str}"


def _strip_macos_app() -> None:
    """strip macOS .app 包中的调试符号以减小体积"""
    if platform.system() != "Darwin":
        return
    app_path = DIST / f"{NAME}.app"
    if not app_path.exists():
        return
    print("\n🔪 正在 strip 调试符号...")
    # strip 所有 .so 和 .dylib 文件
    count = 0
    saved = 0
    for f in app_path.rglob("*.so"):
        size_before = f.stat().st_size
        subprocess.run(["strip", "-x", str(f)], capture_output=True)
        size_after = f.stat().st_size
        saved += size_before - size_after
        count += 1
    for f in app_path.rglob("*.dylib"):
        size_before = f.stat().st_size
        subprocess.run(["strip", "-x", str(f)], capture_output=True)
        size_after = f.stat().st_size
        saved += size_before - size_after
        count += 1
    print(f"   strip 了 {count} 个文件，节省 {saved / 1024 / 1024:.1f} MB")


def _clean_opencv_dylibs() -> None:
    """删掉 opencv 中 WormTracker 不需要的 FFmpeg dylib（音频/流媒体/OCR/X11等）"""
    app_path = DIST / f"{NAME}.app"
    dylib_dir = app_path / "Contents" / "Frameworks" / "cv2" / "__dot__dylibs"
    if not dylib_dir.exists():
        return

    print("\n🧹 清理 opencv 无用 dylib...")
    before = sum(f.stat().st_size for f in dylib_dir.rglob("*.dylib"))

    # WormTracker 只需要: 视频解码 (H.264/HEVC/VP9/AV1) + 基础图片 (JPEG/PNG/GIF) + 容器格式 (MP4/MOV/AVI/MKV)
    # 以下全部是多余的，安全删除
    _KEEP_PREFIXES = {
        "libaom", "libavcodec", "libavformat", "libavutil",
        "libbrotli", "libcrypto", "libdav1d",
        "libfontconfig", "libfreetype", "libfribidi",
        "libgif", "libglib", "libgraphite2", "libharfbuzz",
        "libhwy", "libintl", "libjpeg", "liblz4", "liblzma",
        "libmbedcrypto", "libogg", "libpcre2", "libpng16",
        "libsnappy", "libssl", "libswresample", "libswscale",
        "libvmaf", "libvpx", "libx264", "libzstd",
    }
    removed = 0
    for f in sorted(dylib_dir.glob("*.dylib")):
        keep = any(f.name.startswith(p) for p in _KEEP_PREFIXES)
        if not keep:
            f.unlink()
            removed += 1

    after = sum(f.stat().st_size for f in dylib_dir.rglob("*.dylib"))
    print(f"   删除了 {removed} 个无用 dylib，节省 {(before - after) / 1024 / 1024:.1f} MB")


def build(args: argparse.Namespace) -> int:
    """执行打包"""
    print(f"{'='*60}")
    print(f"  WormTracker 打包工具")
    print(f"  平台: {platform.system()} {platform.machine()}")
    print(f"  Python: {sys.version}")
    print(f"{'='*60}\n")

    # 1. 检查 PyInstaller
    if not check_pyinstaller():
        print("❌ 未安装 PyInstaller，请先安装:")
        print("   pip install pyinstaller")
        return 1

    import PyInstaller
    print(f"✅ PyInstaller {PyInstaller.__version__}\n")

    # 2. 清理
    if args.clean:
        clean_build()

    # 3. 确保 spec 文件存在
    if not SPEC_FILE.exists():
        print(f"❌ 找不到 spec 文件: {SPEC_FILE}")
        return 1

    # 4. 构建 PyInstaller 命令
    cmd = [
        sys.executable, "-m", "PyInstaller",
    ]
    if args.clean:
        cmd.append("--clean")
    cmd.append(str(SPEC_FILE))

    print("🔨 正在打包...")
    print(f"   命令: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print("\n❌ 打包失败!")
        return result.returncode

    print("\n✅ 打包完成!")

    # 5. macOS: strip 调试符号瘦身
    _strip_macos_app()
    _clean_opencv_dylibs()

    # 6. 显示输出
    plat = platform.system()
    if plat == "Darwin":
        app_path = DIST / f"{NAME}.app"
        exe_path = DIST / NAME
        if app_path.exists():
            print(f"\n📦 macOS 应用包: {app_path}")
            print(f"   可双击运行或拖入 /Applications")
        if exe_path.exists():
            print(f"\n📦 macOS 可执行文件: {exe_path}")
    elif plat == "Windows":
        exe_path = DIST / f"{NAME}.exe"
        if exe_path.exists():
            print(f"\n📦 Windows 可执行文件: {exe_path}")

    # 6. 生成 zip (可选)
    if args.zip:
        zip_name = f"{get_output_name()}.zip"
        zip_path = ROOT / zip_name
        print(f"\n📦 正在生成压缩包: {zip_name}")

        # 构建要打包的文件列表
        import zipfile
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            dist_root = DIST
            for f in dist_root.rglob("*"):
                if f.is_file():
                    arcname = f.relative_to(dist_root)
                    zf.write(f, arcname)
                    print(f"   + {arcname}")

        print(f"\n✅ 压缩包已生成: {zip_path}")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="WormTracker 跨平台打包工具"
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="清理旧的构建产物后重新打包",
    )
    parser.add_argument(
        "--zip", action="store_true",
        help="打包后额外生成 zip 压缩包便于分发",
    )
    args = parser.parse_args()

    return build(args)


if __name__ == "__main__":
    sys.exit(main())
