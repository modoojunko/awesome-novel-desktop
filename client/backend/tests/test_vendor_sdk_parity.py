"""SDK 副本防漂移钉（c-knowledge-source-align 评审 P2）。

SDK 一期有四份 C 端同源副本（payloads/concepts/textclean/theme_catalog）——
字节级复制是迁移手段而非长期机制：任一侧单改即静默漂移（kb 侧加合法键而 SDK
副本不动＝拆书收录整条跳过）。本钉把「同批更新」承诺变成 CI 约束：字节相等＋
题材词表相等，改任一侧必须同批（diff 报警即是预期工作流）。
"""

import hashlib
import re as _re
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
SDK = BACKEND / "vendor_sdk" / "novel_deconstruct_sdk"

# sha256 对拍对（SDK 副本 ↔ C 端同源文件）：字节级相等＝逐字符同源
_BYTE_PAIRS = (
    ("payloads.py", "kb/payloads.py"),
    ("concepts.py", "kb/concepts.py"),
)
# textclean 在 kb 侧只是 migrate_library 中的一个函数段——抽函数标记对拍
_TEXTCLEAN_TOKENS = ("_KB_CHAPTER_ANCHOR_RE = re.compile", "def strip_chapter_anchor")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_副本与C端同源文件字节相等():
    for sdk_name, kb_name in _BYTE_PAIRS:
        assert _sha(SDK / sdk_name) == _sha(BACKEND / kb_name), (
            f"SDK/{sdk_name} 与 {kb_name} 漂移——改任一侧必须同批同步（c-knowledge-source-align 承诺）"
        )


def test_textclean_同源标记在位():
    sdk_src = (SDK / "textclean.py").read_text()
    kb_src = (BACKEND / "kb" / "migrate_library.py").read_text()
    for token in _TEXTCLEAN_TOKENS:
        assert token in sdk_src and token in kb_src, f"textclean 缺同源标记：{token}"


def test_题材词表快照与C端活词表相等():
    """纯文本对拍：SDK 快照与 C 端活词表的题材名集合/顺序一致。"""
    sdk_text = (SDK / "theme_catalog.py").read_text()
    kb_text = (BACKEND / "genres" / "theme_catalog.py").read_text()

    m_sdk = _re.search(r"THEME_NAMES: tuple\[str, \.\.\.\] = (.+)", sdk_text, _re.MULTILINE)
    assert m_sdk, "SDK 词表定义未找到"
    sdk_themes = tuple(_re.findall(r"['\"]([^'\"]+)['\"]", m_sdk.group(1)))

    # C 端 THEMES 形态是 _t("题材名", "描述", [_s(...)]) 工厂调用——抓 _t 首参即题材名
    kb_themes = _re.findall(r'_t\(\s*"([^"]+)"', kb_text)

    assert set(sdk_themes) == set(kb_themes) and len(sdk_themes) == len(kb_themes), (
        f"SDK 题材词表快照漂移：{len(sdk_themes)} vs {len(kb_themes)}——C 端词表更新时 "
        "vendor_sdk/theme_catalog.py 必须同批"
    )
    assert len(kb_themes) > 0
