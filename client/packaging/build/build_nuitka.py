#!/usr/bin/env python3
"""build_nuitka.py — Nuitka 构建引擎（c-nuitka-full；BUILD_ENGINE=nuitka 时打包链走这里）。

与 PyInstaller（build.spec）双引擎并存：烘焙清单同源 bundle_manifest.py（分叉即失真，
死条目判例见该文件 docstring）；交付形态等价——macOS 出 `AI Novel.app`，Windows 出
`AI Novel/` onedir（installer.iss 可直接消费）。

用法：
    python build_nuitka.py                 # 当前平台 standalone（清单/数据全烘焙）
    python build_nuitka.py --out dist-nuitka

前置：
    - 前端已构建（client/frontend/dist/index.html 存在）
    - Windows：version_info.txt 已生成（build.bat 在调用本脚本前生成；缺即失败不兜底）
    - `pip install nuitka ordered-set`＋平台 C 编译器（mac=clang / win=MSVC）

spike 判例（2026-10-07）：
    - `--macos-create-app-bundle` 自身蕴含 standalone，不能与 `--mode=` 并用（FATAL）；
    - datas 落 .app/Contents/MacOS/（与二进制同目录），交付树天然零 .py/.pyc；
    - 全清单 --include-module 显式列出比依赖自动 follow 稳。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
CLIENT = HERE.parent.parent          # build/ -> packaging/ -> client/
REPO = CLIENT.parent                 # 仓库根
BACKEND = CLIENT / "backend"
APP_NAME = "AwesomeNovel"  # 与 build.spec EXE/COLLECT、installer.iss Source 同名（改名单源 #687）

# Windows 控制台默认 cp1252，编不了中文输出（#705/13f5f4d4 同款判例）——
# 本脚本中文日志多，入口处统一兜底 UTF-8；GUI/重定向态 stdout 可能为 None
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def _fail(msg: str) -> None:
    raise SystemExit(f"build_nuitka: {msg}")


def _ensure_native_extensions() -> None:
    """阶段二前置（c-prompt-pack-hardening）：prompt_pack 原生扩展不存在就就地编译。

    平台后缀随解释器走（cpython-312-darwin.so / win_amd64.pyd）；扩展缺失时
    Nuitka 会退编 .py 进主二进制——不可读性等价但扫描门红（NATIVE 在位判失败），
    所以这里补齐而非带病出包；失败即停，不允许静默字节码回落。
    """
    import glob

    sys.path.insert(0, str(HERE))
    if glob.glob(str(BACKEND / "prompt_pack" / "*.so")) or glob.glob(
        str(BACKEND / "prompt_pack" / "*.pyd")
    ):
        return
    print("build_nuitka: prompt_pack 原生扩展缺失，先跑 compile_native.py …")
    r = subprocess.run([sys.executable, str(HERE / "compile_native.py")], cwd=str(HERE))
    if r.returncode != 0:
        _fail("compile_native 失败——拒绝出包（阶段二不静默回落字节码）")


def build(out_dir: Path) -> Path:
    sys.path.insert(0, str(HERE))
    import bundle_manifest as M

    _ensure_native_extensions()

    frontend_index = REPO / "client/frontend/dist/index.html"
    if not frontend_index.exists():
        _fail("前端未构建：client/frontend/dist/index.html 不存在——先在 client/frontend 跑 npm run build")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND) + os.pathsep + env.get("PYTHONPATH", "")

    cmd = [sys.executable, "-m", "nuitka", "--assume-yes-for-downloads",
           f"--output-dir={out_dir.name}", "--report=compilation-report.xml"]

    if sys.platform == "darwin":
        cmd += ["--macos-create-app-bundle",  # 蕴含 standalone（spike 判例，勿加 --mode=）
                f"--macos-app-name={APP_NAME}",
                f"--macos-app-icon={HERE / 'icon.icns'}"]
    elif sys.platform == "win32":
        cmd += [f"--windows-icon-from-ico={HERE / 'icon.ico'}",
                "--windows-console-mode=disable"]
        # Nuitka 4.x 无 version-info 文件选项（演练判例：--windows-version-file 不存在），
        # 用离散旗标；字段与 PyInstaller 的 version_info.txt 同一单源（win_version_info）
        import win_version_info
        fields = win_version_info.collect(root_dir=REPO)
        if fields is None:
            _fail("Windows 版本资源字段收集失败——检查 brand/brand.json 字段门禁输出")
        cmd += [
            f"--company-name={fields['publisher']}",
            f"--product-name={fields['brand_name']}",
            f"--file-version={fields['file_version']}",
            f"--product-version={fields['file_version']}",
            f"--file-description={fields['brand_name']} ({fields['brand_name_en']})",
            f"--copyright=© {fields['publisher']}",
        ]
    else:
        _fail(f"平台未支持：{sys.platform}")

    for m in M.HIDDEN_IMPORTS:
        cmd.append(f"--include-module={m}")
    for m in M.EXCLUDED_IMPORTS:
        cmd.append(f"--nofollow-import-to={m}")
    for src, dest in M.DATAS:
        p = REPO / src
        if not p.exists():
            _fail(f"datas 缺失：{p}")
        # dest 语义适配：清单按 PyInstaller 口径（"."＝资源根）；Nuitka 的 dest 是
        # 「目标目录」，"." 会让签名清单混入 `Contents/MacOS/.` 目录项 → codesign
        # 必 FATAL「bundle format unrecognized」（spike 文件名 dest 成功判例）——
        # 文件条目落资源根时翻译成文件名 dest。
        rel = os.path.relpath(p, HERE)
        if p.is_dir():
            cmd.append(f"--include-data-dir={rel}={dest}")
        else:
            cmd.append(f"--include-data-file={rel}={p.name if dest == '.' else dest}")
    for src, dest in M.CONDITIONAL_DATAS:  # release.json 仅发布期存在（CI 烘焙）
        p = HERE / src
        if p.exists():
            cmd.append(f"--include-data-file={os.path.relpath(p, HERE)}={p.name if dest == '.' else dest}")
    cmd.append("pywebview_app.py")

    t0 = time.time()
    r = subprocess.run(cmd, env=env, cwd=HERE)
    if r.returncode != 0:
        _fail(f"Nuitka 退出码 {r.returncode}（日志见上／compilation-report.xml）")
    elapsed = time.time() - t0
    print(f"build_nuitka: 编译完成 {elapsed:.0f}s")

    # ── 交付名对齐：Windows onedir 与 macOS .app 都改名 AI Novel（installer/DMG 期望；
    # Nuitka 的 bundle 目录名跟入口脚本走，--macos-app-name 只写 Info.plist）
    if sys.platform == "win32":
        raw = out_dir / "pywebview_app.dist"
        target = out_dir / APP_NAME
        if target.exists():
            shutil.rmtree(target)
        raw.rename(target)
        dist_root = target
    else:
        raw = out_dir / "pywebview_app.app"
        target = out_dir / f"{APP_NAME}.app"
        if target.exists():
            shutil.rmtree(target)
        raw.rename(target)
        dist_root = target / "Contents/MacOS"

    # 构建指纹：产物内可自证「哪个引擎、哪个版本构建」（排障与验收判据）
    try:
        git = subprocess.run(["git", "describe", "--tags", "--always", "--dirty"],
                             capture_output=True, text=True, cwd=str(REPO), timeout=5)
        rev = git.stdout.strip() if git.returncode == 0 else "unknown"
    except OSError:
        rev = "unknown"
    nuitka_ver = subprocess.run([sys.executable, "-m", "nuitka", "--version"],
                                capture_output=True, text=True, timeout=30).stdout.strip().splitlines()[0]
    (dist_root / "build-engine.json").write_text(json.dumps({
        "engine": "nuitka", "nuitka_version": nuitka_ver,
        "python_version": sys.version.split()[0], "platform": sys.platform,
        "git": rev, "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "compile_seconds": round(elapsed),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"build_nuitka: 指纹已写 {dist_root / 'build-engine.json'}")
    return dist_root


def main() -> None:
    ap = argparse.ArgumentParser(description="Nuitka 打包引擎（清单同源 bundle_manifest）")
    ap.add_argument("--out", default="dist-nuitka", help="输出目录（默认 dist-nuitka）")
    args = ap.parse_args()
    out_dir = (HERE / args.out).resolve()
    result = build(out_dir)
    print(f"build_nuitka: 交付根 = {result}")


if __name__ == "__main__":
    main()
