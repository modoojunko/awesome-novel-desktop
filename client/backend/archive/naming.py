"""归档文件命名单源（c-archive-filename-safety）。

形态：`{chapter_ref}-{slug(标题)}.md`。全部消费方（归档列表/GET 的寻址、归档写接口的
`archive_path`、备份导出与包内 manifest）一律经本模块，**禁止再手抄公式**——两处手抄
副本正是本 change 的缺陷来源。

slug 安全规则（守卫生效的前提，见 change design 的实证表）：
- 路径分隔符（`/`、`\\`）→ `-`：条目名不得含分隔符（zip 布局/URL 路径面）；
- 连续点（`..` 及以上）收敛为单点：`_parse_archive_filename` 拒 `..` 子串，
  不收敛则「列表有、打不开」；
- **截断之后**剥首尾点：slug 尾部点与拼接的 `.md` 会形成 `..` 子串
  （评审 P0 反例：`"a"*49 + "."`），截断前剥不够。
"""

import re

_SEP_RE = re.compile(r"[\\/]")
_DOTS_RE = re.compile(r"\.{2,}")


def slugify(title: str) -> str:
    s = (title or "").replace(" ", "-").lower()
    s = _SEP_RE.sub("-", s)   # 路径分隔符 → 连字符
    s = _DOTS_RE.sub(".", s)  # 连续点收敛为单点
    return s[:50].strip(".")  # 截断之后剥首尾点（截断边界防护，见模块 docstring）


def archive_filename(chapter_ref: str, title: str) -> str:
    """归档文件名（文件时代的寻址形态，前端零改动继续用它当地址）。"""
    return f"{chapter_ref}-{slugify(title)}.md"


def parse_archive_filename(filename: str) -> tuple[str, str] | None:
    """'vol-1-ch-2-标题.md' → ('vol-1-ch-2', 标题 slug)；形态不符返回 None。"""
    if "/" in filename or "\\" in filename or ".." in filename or not filename.endswith(".md"):
        return None
    body = filename[:-3]
    parts = body.split("-")
    if len(parts) < 4 or parts[0] != "vol" or parts[2] != "ch":
        return None
    if not (parts[1].isdigit() and parts[3].isdigit()):
        return None
    ref = f"vol-{parts[1]}-ch-{parts[3]}"
    slug = "-".join(parts[4:])
    return ref, slug
