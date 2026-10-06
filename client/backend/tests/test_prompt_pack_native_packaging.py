"""c-prompt-pack-hardening 阶段二门禁：原生扩展必须进产物，且不得回落到字节码。

两条不变量（对应 tasks 4.2/4.3/4.4）：
  1. **扫描器本身可靠**：产物里缺原生扩展、或出现敏感模块的 .py/.pyc → 必须报问题
     （反证：把解密路径"改回纯 Python"＝产物里只有字节码 → 扫描必须红）；
  2. **接线不可被静默摘掉**：CI 与本地打包脚本都含「编译」与「扫描」两步，build.spec
     显式列了 prompt_pack 系列（懒导入被静态分析漏掉＝冻结包缺模块），requirements 含 cython。

「同一套测试在 .py 与 .so 两态都跑」的实证在交付说明里（两种形态各 39 条全绿）；本文件
只钉机器可判的部分。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
COMPILE_SCRIPT = REPO / "client" / "packaging" / "build" / "compile_native.py"
CI_PACKAGE = REPO / ".github" / "workflows" / "client-package.yml"
BUILD_RELEASE = REPO / "client" / "packaging" / "build" / "build_release.ps1"
BUILD_SPEC = REPO / "client" / "packaging" / "build" / "build.spec"
REQUIREMENTS = REPO / "client" / "packaging" / "build" / "requirements.txt"


def _compile_native():
    spec = importlib.util.spec_from_file_location("compile_native_under_test", COMPILE_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_bundle(root: Path, *, shape: str) -> Path:
    """造一个合成产物目录：native＝三项扩展齐全；bytecode＝只有 .pyc（阶段二被摘掉）。"""
    pkg = root / "_internal" / "prompt_pack"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.pyc").write_bytes(b"x")
    for stem in ("localkey", "container", "sync"):
        if shape == "native":
            (pkg / f"{stem}.cpython-312-test.so").write_bytes(b"x")
        else:
            (pkg / f"{stem}.pyc").write_bytes(b"x")
    return root


def test_scanner_passes_on_native_bundle(tmp_path):
    mod = _compile_native()
    assert mod.scan_bundle(str(_fake_bundle(tmp_path / "ok", shape="native"))) == []


def test_scanner_flags_missing_extension(tmp_path):
    """缺原生扩展＝阶段二没打进包 → 扫描必须红。"""
    mod = _compile_native()
    problems = mod.scan_bundle(str(tmp_path / "empty"))
    assert problems, "空产物竟然通过了"
    assert all("原生扩展" in p for p in problems), problems


def test_scanner_flags_bytecode_fallback(tmp_path):
    """反证（探针）：产物里只剩字节码（＝把解密路径改回纯 Python / 编译步骤被摘掉）→ 必须红。"""
    mod = _compile_native()
    problems = mod.scan_bundle(str(_fake_bundle(tmp_path / "bc", shape="bytecode")))
    assert any("可反编译形态" in p for p in problems), problems
    assert any("缺原生扩展" in p for p in problems), problems


def test_packaging_chains_are_wired():
    """CI 与本地打包脚本都必须「先编译、后打 PyInstaller、再扫产物」——缺一步等于阶段二失效。"""
    ci = CI_PACKAGE.read_text(encoding="utf-8")
    assert "Compile prompt-pack native modules (Cython)" in ci, "CI 缺编译步骤"
    assert "compile_native.py --scan" in ci, "CI 缺产物扫描闸门"
    assert ci.index("Compile prompt-pack native modules") < ci.index("name: Build app (PyInstaller)"), (
        "编译必须在 PyInstaller 之前（否则打进包的是旧字节码）"
    )

    ps1 = BUILD_RELEASE.read_text(encoding="utf-8")
    assert "python compile_native.py" in ps1, "本地打包脚本缺编译步骤"
    assert "compile_native.py --scan" in ps1, "本地打包脚本缺产物扫描闸门"

    spec = BUILD_SPEC.read_text(encoding="utf-8")
    for mod in ("prompt_pack", "prompt_pack.container", "prompt_pack.localkey", "prompt_pack.sync"):
        assert f"'{mod}'" in spec, f"build.spec 未显式列出 {mod}（懒导入会被静态分析漏掉）"

    assert "cython" in REQUIREMENTS.read_text(encoding="utf-8").lower(), "打包依赖缺 cython"


def test_native_modules_are_listed_in_script():
    """编译清单＝钥匙/解密/同步器三块；核心假设（这三块含密钥材料与解密参数）不得被悄悄改小。"""
    mod = _compile_native()
    assert set(mod.NATIVE_MODULES) == {
        "prompt_pack.localkey",
        "prompt_pack.container",
        "prompt_pack.sync",
    }, mod.NATIVE_MODULES


def test_local_tree_compiled_artifacts_are_ignored():
    """就地编译产物（.so/.pyd）不得入库（否则 Windows 包会带上 macOS 二进制）。"""
    gi = (REPO / ".gitignore").read_text(encoding="utf-8")
    assert "client/backend/prompt_pack/*.so" in gi and "client/backend/prompt_pack/*.pyd" in gi

