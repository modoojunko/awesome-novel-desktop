# backend/build_info.py
"""构建信息自报（c-version-build-info）：dev 构建给出「分支＋commit 短串」，界面据此精确到构建。

- 独立零依赖叶子（与 schema_version.py 并列）：不 import fastapi/httpx，测试与
  CI 组件脚本可直接驱动；update_check.py 只做载荷装配，不再塞 git subprocess。
- **dev 总闸前置**：本机版本非 dev（tag 构建）一律 None——env 路径也在闸内，
  tag 构建机器上的杂散 CLIENT_BUILD_* 不破坏「tag 构建构建信息为空」契约。
- 闸内来源优先级：CLIENT_BUILD_BRANCH/CLIENT_BUILD_COMMIT **两键都非空**才用 env
  （单键缺失按 None 是有意：展示格式 `{branch}@{commit}` 需要成对，不引入
  「只显分支」的第二种 UI 口径）；否则惰性读一次 git（frozen 包跳过——安装包
  无 .git，subprocess 纯浪费）。
- 清洗按来源分治：env/烘焙路径字符集清洗（防烘焙脏串，纵深防御）；git 路径
  **不清洗**（字符集不含 `/`，feature/foo 会洗坏），仅截断＋剥控制字符。
- commit 形态宽容 `[0-9a-f]{5,40}`：`git rev-parse --short=5` 是「至少 5 位」
  语义，对象碰撞的仓库会自动加长；展示端统一截前 5 位（前端 formatVersion）。
- 失败一律静默 None：构建信息是诊断增益，绝不影响版本自报与更新检测主链。
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import sys

from schema_version import DEV_VERSION, app_version

logger = logging.getLogger(__name__)

_COMMIT_RE = re.compile(r"[0-9a-f]{5,40}")
_ENV_BRANCH_BAD = re.compile(r"[^A-Za-z0-9._-]")

_MAX_BRANCH_LEN = 40
_TIMEOUT = 2.0

# 模块级缓存：_UNSET=还没读过 / None=读过且没有 / tuple=读过且有。必须是可被
# monkeypatch.setattr 整体替换的模块变量——pytest 进程非 frozen 且仓库有 .git，
# 不可复位的缓存会把真实 git 信息带进后面打桩的用例（顺序依赖假绿假红）。
_UNSET = object()
_git_build: object = _UNSET


def get_build_info(current_version: str | None = None) -> dict | None:
    """构建信息 `{branch, commit} | None`；current_version 缺省时取版本自报单源。"""
    if current_version is None:
        current_version = app_version()
    if current_version != DEV_VERSION:
        return None

    branch = (os.environ.get("CLIENT_BUILD_BRANCH") or "").strip()
    commit = (os.environ.get("CLIENT_BUILD_COMMIT") or "").strip().lower()
    if branch and commit and _COMMIT_RE.fullmatch(commit):
        cleaned = _clean_env_branch(branch)
        if cleaned:
            return {"branch": cleaned, "commit": commit}

    got = _read_git_build()
    return {"branch": got[0], "commit": got[1]} if got else None


def _clean_env_branch(value: str) -> str:
    """env/烘焙路径清洗：非法字符替换 `-`（与 CI 侧 tag 清洗同一手法）＋截断。"""
    return _ENV_BRANCH_BAD.sub("-", value.strip())[:_MAX_BRANCH_LEN]


def _read_git_build() -> tuple[str, str] | None:
    """git 工作区 → (branch, commit 短串)；结果进程级缓存一次。"""
    global _git_build
    if _git_build is _UNSET:
        _git_build = _read_git_build_once()
    return _git_build  # type: ignore[return-value]


def _read_git_build_once() -> tuple[str, str] | None:
    if getattr(sys, "frozen", False):
        return None
    # cwd 钉到本文件目录（仓库检出内任意子目录 git 均可达），不赌进程工作目录
    cwd = os.path.dirname(os.path.abspath(__file__))
    try:
        def _run(*args: str) -> str:
            return subprocess.run(
                ["git", *args], capture_output=True, text=True,
                timeout=_TIMEOUT, cwd=cwd, check=True,
            ).stdout.strip()

        commit = _run("rev-parse", "--short=5", "HEAD").lower()
        branch = _run("rev-parse", "--abbrev-ref", "HEAD")
    except (OSError, subprocess.SubprocessError) as exc:
        # git 未装（Windows 立即 FileNotFoundError）/超时/非 git 目录 → 同为静默 None
        logger.debug("build_info: git 不可用，构建信息降级为空：%r", exc)
        return None
    if not _COMMIT_RE.fullmatch(commit) or not branch:
        return None
    branch = "".join(ch for ch in branch if ch.isprintable())[:_MAX_BRANCH_LEN]
    if not branch:
        return None
    return branch, commit  # detached HEAD 时 branch 为字面量 "HEAD"，展示可接受
