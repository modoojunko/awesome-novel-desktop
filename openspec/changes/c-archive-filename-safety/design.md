## Context

- 两份 slug 副本：`archive/router.py::_slugify`（:28）与 `archive/service.py:55` 内联（后者按 vol/ch 数字拼 `archive_path`，随 POST 归档响应返回，:127）；`_archive_filename` 另有消费方 `backup/export.py:83`、`novels/router.py:618/700`。
- 守卫：`_parse_archive_filename`（router.py:37）拒 `"/"` 与 `".."` 子串；`validate_paths`（importer.py:31-35）拒绝对路径与**独立 `..` 路径段**。
- 实证四行（proposal 表）：`上/下`（嵌套+stem 截断）、`上/../下`（整包 422）、`第1..2章`（GET 不可寻址）、`"a"*49+"."`（**截断边界**：slug 尾点 + `.md` → `..` 子串）。

## Goals / Non-Goals

**Goals:**
- 规则单源（`archive/naming.py`），条目名通过路径校验、恒可解析；写接口与列表同源；普通标题零漂移。
- 截断边界不产生 `..`（评审 P0 反例必须被测试钉死）。

**Non-Goals:**
- 不改两个守卫（守卫是对的）；不做真标题保真（manifest.title 优先）与 Windows 保留字符清洗、`r{8hex}` 前缀误判——见 proposal Non-Goals。
- 不删/不重写历史包中的坏条目名。

## Decisions

**1. 新建 `archive/naming.py` 为唯一公式源；router/service 改薄。**
```python
# naming.py
_SEP_RE = re.compile(r"[\\/]")
_DOTS_RE = re.compile(r"\.{2,}")

def slugify(title: str) -> str:
    s = (title or "").replace(" ", "-").lower()
    s = _SEP_RE.sub("-", s)      # 路径分隔符 → 连字符
    s = _DOTS_RE.sub(".", s)     # 连续点收敛为单点
    return s[:50].strip(".")     # 截断之后剥首尾点——防截断边界与 ".md" 拼出 ".."（评审 P0）

def archive_filename(chapter_ref: str, title: str) -> str:
    return f"{chapter_ref}-{slugify(title)}.md"

def parse_archive_filename(filename): ...  # 原实现原样迁移
```
`archive/router.py` 从 naming 导入并保留 `_archive_filename = archive_filename`、`_parse_archive_filename = parse_archive_filename` 两个别名（`backup/export.py`、`novels/router.py` 的既有 import 面零改动）；`_slugify` 无外部消费方、未保留（ruff 会删未用别名）；`archive/service.py` 用 `archive_filename(chapter_ref, title)` 取代内联公式（ref 即 `vol-{vol}-ch-{ch}` 的规范形，比按章数据数字拼更正确——数据与 ref 不一致时以 ref 为准）。

变换管线顺序与旧实现的前两步（`replace(" ")`、`lower()`）完全一致，仅追加安全步与「截断后剥点」；无点、无分隔符标题输出逐字节不变。

**2. 反例驱动的测试表（单元参数化 + 端到端）。**
单元逐 case：四行实证表 + `"a"*49+"."`、`"a"*49+".bcdef"`（截断边界两形态）、空串、纯空格、`a\b`、`第1章.`、`.x`、普通标题零漂移（含 50 字截断窗口内无点标题）。端到端：危险标题书 → 导出 → 条目名断言（无分隔符/无 `..` 子串/`".." not in parts`）+ `validate_paths` 通过 + `parse_archive_filename(filename)` 非 None；导入恢复 title=完整 stem 语义断言。写接口同源：归档 POST 的 `archive_path` basename == 列表 `filename`（`test_archive_free.py` 模式复用）。
「`上/下` 不可走真路由断言」（FastAPI 路径参数容不下 `/`）：该形态的寻址问题由单元层 `parse_archive_filename` 覆盖，路由层只测 `第1..2章` 类（slash-free）。

**3. 先红口径。**
单元：修复前 `上/../下` 输出含 `/`、`第1..2章` parse 返回 None、`"a"*49+"."` 全名含 `..` —— 三处必红。端到端：修复前导出即产 `..` 段（validate_paths 拒）——必红。

## Risks / Trade-offs

- [与 service.py 不同源的半修会引入接口自相矛盾] → 本 change 的 tasks 把「两处副本同时改经 naming」列为验收前置；spec 加写接口/列表同源条款兜底。
- [历史包坏条目名] → 一次性产物无重写通道，Non-Goal 登记。

## Migration Plan

新增模块 + 两处改薄 + 测试，一次 commit；无迁移。回滚 = revert。

## Open Questions

无。
