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

    # c-nuitka-full 清单单源化：datas/hiddenimports 抽进 bundle_manifest（双引擎共同
    # 消费），「显式列出」的闸门意图改钉单源——懒导入被静态分析漏掉＝冻结包缺模块
    # ＝运行期解密崩，这条底线不随清单搬家而松动。
    manifest_spec = importlib.util.spec_from_file_location(
        "bundle_manifest_under_test", REPO / "client" / "packaging" / "build" / "bundle_manifest.py"
    )
    assert manifest_spec and manifest_spec.loader
    manifest = importlib.util.module_from_spec(manifest_spec)
    manifest_spec.loader.exec_module(manifest)
    for mod in ("prompt_pack", "prompt_pack.container", "prompt_pack.localkey", "prompt_pack.sync"):
        assert mod in manifest.HIDDEN_IMPORTS, f"烘焙清单未显式列出 {mod}（懒导入会被静态分析漏掉）"
    assert "import bundle_manifest" in BUILD_SPEC.read_text(encoding="utf-8"), (
        "build.spec 未消费清单单源——内联手抄会漂移（死条目判例）"
    )

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

def test_scanner_ignores_same_named_files_outside_our_package(tmp_path):
    """评审 P1 回归：依赖里就有同名文件（实测 anthropic/types/container.py、
    httpcore/_backends/sync.py、sqlalchemy/orm/sync.py）——扫描必须只认 `prompt_pack`
    包目录内的文件，否则发版会被误判红（打包链只在 tag 跑，第一次发现就是发版日）。"""
    mod = _compile_native()
    root = _fake_bundle(tmp_path / "dep", shape="native")
    for rel in ("anthropic/types", "httpcore/_backends", "sqlalchemy/orm"):
        d = root / "_internal" / rel
        d.mkdir(parents=True, exist_ok=True)
        for n in ("container.py", "sync.py", "localkey.py", "container.pyc", "sync.pyc"):
            (d / n).write_bytes(b"x")
    assert mod.scan_bundle(str(root)) == [], "依赖里的同名文件被误判成本模块"
