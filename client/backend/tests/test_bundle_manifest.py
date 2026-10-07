"""打包清单单源诚实性（c-nuitka-full tasks 1.2/1.3）。

死条目判例：`filesystem.composite_storage`／`threads` 退役后仍挂在 build.spec 清单里
——PyInstaller 对缺失 hiddenimport 只告警，Nuitka 直接 FATAL，spike 首轮即被逼出。
本测试把「清单必须诚实」钉进门禁：每个 hiddenimport 必须可解析、datas 源必须存在
（前端 dist 除外——构建产物由两引擎各自的前置断言负责）、零提示词在清单层复断、
两引擎实现都必须消费单源（内联手抄即红）。
"""

import importlib
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
CLIENT = BACKEND.parent
REPO = CLIENT.parent
PACKAGING_BUILD = CLIENT / "packaging" / "build"


def _manifest():
    sys.path.insert(0, str(PACKAGING_BUILD))
    return importlib.import_module("bundle_manifest")


def test_hiddenimports_all_resolvable():
    for name in _manifest().HIDDEN_IMPORTS:
        top = name.split(".")[0]
        if (BACKEND / top).exists():
            # backend 本地模块：整条路径必须真实存在（防退役残留）
            base = BACKEND.joinpath(*name.split("."))
            assert base.is_dir() or Path(f"{base}.py").exists(), f"死条目：{name}"
        else:
            # 三方包用 import 试探（find_spec 对 vendored/namespace 形态会给出
            # __spec__ is None 的假阴性——anthropic 判例）
            import importlib

            try:
                importlib.import_module(name)
            except ImportError as exc:
                raise AssertionError(f"hiddenimport 不可解析：{name}（{exc}）") from exc


def test_retired_modules_absent():
    m = _manifest()
    assert "filesystem.composite_storage" not in m.HIDDEN_IMPORTS
    assert "threads" not in m.HIDDEN_IMPORTS


def test_datas_sources_exist_and_no_prompts():
    for src, _dest in _manifest().DATAS:
        if src == "client/frontend/dist":
            continue  # 构建产物：由 build.spec／build_nuitka 前置断言负责
        assert (REPO / src).exists(), f"datas 源缺失：{src}"
    joined = " ".join(dest for _src, dest in _manifest().DATAS)
    assert "prompts" not in joined, "提示词模板禁止回清单（CDN 加密包硬切，c-prompt-pack-client）"


def test_both_engines_consume_manifest():
    m = _manifest()
    for engine in ("build.spec", "build_nuitka.py"):
        text = (PACKAGING_BUILD / engine).read_text(encoding="utf-8")
        assert "import bundle_manifest" in text or "bundle_manifest as" in text, (
            f"{engine} 未消费单源——内联手抄清单会漂移（死条目判例）"
        )
    # 单源本身必须非空（防清单被误清空后测试仍绿的假象）
    assert len(m.HIDDEN_IMPORTS) > 40 and len(m.DATAS) >= 4
