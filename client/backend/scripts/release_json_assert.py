"""release.json 产物断言（c-db-per-version）：CI 冒烟步骤的**唯一实现**。

用法：`python scripts/release_json_assert.py <dist 内 release.json 路径>`

判据（缺失/不一致即非零退出，流水线转红）：
1. 既有三键（S端 地址、版本、检测地址）形态不变；
2. **组件清单 `components` 必须存在**，且 `db_filename` 与后端单源逐字一致；
3. `backup_format_version` 等于后端单源当前值；
4. c-version-build-info：`client_build_branch`/`client_build_commit` **可选键**
   （tag 构建/旧产物不烘），存在则校验形态——分支安全字符集＋≤40、commit
   `[0-9a-f]{5,40}`（`--short=5` 是「至少 5 位」语义，宽容到 40）。
5. c-prompt-pack-delivery：`pack_pubkeys` **必选键**——提示词包验签公钥
   `{"<kid>": "<base64(32B Ed25519)>"}` 的 JSON 串。缺烘＝打包端无钥可验
   （AI 永久「未就绪」），与地址族缺烘同类，冒烟必拦。形态校验单源
   `validate_pack_pubkeys`，生成侧（release_json_generate）同批复用。

脚本化而非 workflow 内联：断言逻辑可被测试直接驱动（正/负例），避免「CI 里那条
断言其实没人跑过」。
"""
from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backup.format import FORMAT_VERSION  # noqa: E402
from schema_version import db_filename_for  # noqa: E402


def validate_pack_pubkeys(raw: object) -> str:
    """c-prompt-pack-delivery：pack_pubkeys 形态校验（生成侧/产物侧共用单源）。

    契约：`{"<kid>": "<base64(32 字节 Ed25519 公钥)>"}` 的 JSON **字符串**
    （存串而非嵌套对象——release.json 各键统一为字符串值，config 白名单亦只放行字符串）。
    空值/非法 JSON/非 dict/空 dict/坏 base64/非 32 字节均判红：**缺烘公钥＝打包端
    永远验不了提示词包**，必须在构建期拦截而不是上线后表现为「AI 恒未就绪」。

    校验通过返回去首尾空白后的原串（生成侧直接写入 release.json）。
    """
    txt = str(raw or "").strip()
    assert txt, "pack_pubkeys 为空（验签公钥未烘入——打包端将无法校验任何提示词包）"
    try:
        keys = json.loads(txt)
    except ValueError:
        raise AssertionError(f"pack_pubkeys 非合法 JSON：{txt[:120]!r}") from None
    assert isinstance(keys, dict) and keys, ("pack_pubkeys 应为非空 {kid: base64} 映射", txt[:120])
    for kid, val in keys.items():
        try:
            key_bytes = base64.b64decode(str(val), validate=True)
        except Exception:
            raise AssertionError(f"pack_pubkeys[{kid}] 非法 base64：{val!r}") from None
        assert len(key_bytes) == 32, (
            f"pack_pubkeys[{kid}] 应为 32 字节 Ed25519 公钥（实得 {len(key_bytes)} 字节）")
    return txt


def check_release_json(path: str | Path) -> dict:
    """校验并返回 release.json 内容；任一断言失败抛 AssertionError。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    # S端 地址族四键（c-package-public-endpoints）：存在且 https 形态——
    # public_server_api 缺烘曾致打包端授权页 404（v0.23–v0.25 实锤），冒烟必拦
    for key in ("server_api_base", "server_api_fallback", "public_server_api", "portal_url"):
        assert str(data.get(key, "")).startswith("https://"), (f"release.json 键 {key} 缺失或非 https", data)
    # c-prompt-pack-delivery：提示词包公钥必选——缺烘＝打包端无钥可验，AI 永久未就绪
    validate_pack_pubkeys(data.get("pack_pubkeys", ""))
    version = str(data.get("client_version", "")).strip()
    assert version, data
    assert str(data.get("client_update_url", "")).startswith("https://"), data
    assert str(data.get("client_update_url_fallback", "")).startswith("https://"), data
    comp = data.get("components")
    assert isinstance(comp, dict), ("release.json 缺 components 键（组件清单未烘入产物）", data)
    assert comp.get("db_filename") == db_filename_for(version), (
        "components.db_filename 与后端单源不一致", comp, version)
    assert comp.get("backup_format_version") == FORMAT_VERSION, (
        "components.backup_format_version 与后端单源不一致", comp, FORMAT_VERSION)
    branch = data.get("client_build_branch")
    commit = data.get("client_build_commit")
    if branch is not None or commit is not None:  # 可选键：缺省容忍，存在则成对校验
        assert isinstance(branch, str) and branch and len(branch) <= 40 \
            and re.fullmatch(r"[A-Za-z0-9._-]+", branch), ("client_build_branch 形态非法", branch)
        assert isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{5,40}", commit), (
            "client_build_commit 形态非法", commit)
    return data


def main(argv: list[str]) -> int:
    try:
        # Windows runner stdout 默认 cp1252，失败信息含中文时 print 即 UnicodeEncodeError
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if len(argv) != 2:
        print("usage: release_json_assert.py <release.json>", file=sys.stderr)
        return 2
    try:
        data = check_release_json(argv[1])
    except AssertionError as exc:
        print(f"::error::release.json 产物断言失败：{exc}", file=sys.stderr)
        return 1
    print("baked:", argv[1], "->", data["client_version"], data["client_update_url"],
          "components=", data["components"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
