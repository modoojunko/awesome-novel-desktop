"""主库零模板门禁（c-prompt-source-flip 4.4/5.1）。

提示词唯一源在 awesome-novel-prompts 仓；本仓 SHALL NOT 跟踪任何 .prompt 模板
（loader 与同步器代码不在此列）。组4 阶段以允许清单过渡（存量 58 文件），组5
`git rm` 后收紧为全禁——清单为空集即终态；新增任何 .prompt 都在这里红。
"""

from __future__ import annotations

from pathlib import Path

# 组5 已 git rm：清单为空集＝终态（全禁）。
ALLOWED: frozenset[str] = frozenset(
)

_BACKEND = Path(__file__).resolve().parents[1]


def test_repo_tracks_no_prompt_templates():
    found = sorted(
        str(p.relative_to(_BACKEND)) for p in _BACKEND.rglob("*.prompt")
        if "__pycache__" not in p.parts and ".venv" not in p.parts
    )
    strays = [f for f in found if f not in ALLOWED]
    assert not strays, (
        "主库出现未登记的 .prompt 模板——提示词唯一源在 awesome-novel-prompts 仓，"
        f"不得回植（c-prompt-source-flip）：{strays}"
    )
