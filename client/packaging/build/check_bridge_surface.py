"""打包入口静态门禁：js_api 桥的公开面只许方法（c-shell-hang-hardening 1.3）。

为什么需要它：pywebview 注入 JS API 时会**递归遍历** js_api 对象的公开（非 `_` 前缀）属性来
枚举可调用对象（`webview/util.py` `get_functions`：`if name.startswith('_'): continue`）。
桥上任何公开的非方法属性——尤其是指向 `Window`/原生控件的——都会被整棵树拖进遍历：
跨线程 COM 访问全部报错，且可能在某次取值上阻塞（2026-10-06 现场：白屏 + 装载永不完成）。

本门禁在打包 CI（不 import 目标模块，纯 AST）判两件事：
1. `NativeBridge` 类体内不得有公开属性赋值（`x = ...` / `x: T = ...`）；
2. 模块级不得出现 `bridge.<公开名> = ...`。

运行期同款契约由 `client/backend/tests/test_packaging_shell_startup.py` 的守卫测试钉住
（`dir(bridge)` 公开成员必须全部可调用）。两道一起，改动一经提交就会红，不必等到现场白屏。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

TARGET = Path(__file__).with_name("pywebview_app.py")
BRIDGE_CLASS = "NativeBridge"
BRIDGE_INSTANCE = "bridge"


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def find_violations(source: str) -> list[str]:
    tree = ast.parse(source)
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == BRIDGE_CLASS:
            for item in node.body:
                targets: list[ast.expr] = []
                if isinstance(item, ast.Assign):
                    targets = list(item.targets)
                elif isinstance(item, ast.AnnAssign):
                    targets = [item.target]
                for t in targets:
                    if isinstance(t, ast.Name) and _is_public(t.id):
                        bad.append(f"{BRIDGE_CLASS}.{t.id}（第 {item.lineno} 行）")
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if (
                    isinstance(t, ast.Attribute)
                    and isinstance(t.value, ast.Name)
                    and t.value.id == BRIDGE_INSTANCE
                    and _is_public(t.attr)
                ):
                    bad.append(f"{BRIDGE_INSTANCE}.{t.attr}（第 {node.lineno} 行）")
    return bad


def main() -> int:
    # Windows 控制台默认 cp1252：非 ASCII 输出会 UnicodeEncodeError 把门禁自己打挂
    # （2026-10-06 v0.28.2 首发实锤）。输出一律 ASCII，并给 stdout 上 UTF-8 兜底。
    if hasattr(sys.stdout, "reconfigure"):  # 无 tty / 被重定向时没有该方法，直接跳过
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    violations = find_violations(TARGET.read_text(encoding="utf-8"))
    if violations:
        print("::error::js_api bridge exposes public attributes (pywebview recurses into them):")
        for v in violations:
            print("  - " + v)
        return 1
    print(f"OK: {BRIDGE_CLASS} public surface is methods only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
