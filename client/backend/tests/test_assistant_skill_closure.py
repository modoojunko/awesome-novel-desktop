"""agent skill 封闭性护栏钉（★boss 立规 2026-11-18★）。

铁律：动作执行一律封装成 skill（服务端封闭工具），大模型只做语言理解与决策
用哪个 skill——SHALL NOT 让模型现写代码执行。

钉两面：
1. 注册表封闭：TOOL_REGISTRY 每个工具都有服务端 fn（模型决策面只到「选工具
   ＋填参数」，够不到任意代码）；
2. 助手模块无可执行面：assistant/ 全模块源码无 eval/exec/动态导入——模型输出
   永远被当作数据解析（ast.literal_eval 抢救解析与 re.compile 白名单）。
"""

from pathlib import Path

from assistant.tools import TOOL_REGISTRY, ToolContext, run_tool

_ASSISTANT_DIR = Path(__file__).resolve().parent.parent / "assistant"
# 白名单：字面量数据解析（协议 JSON 抢救）与正则编译——都不是代码执行
_ALLOWED = ("ast.literal_eval", "re.compile")


def test_registry_all_tools_have_server_side_fn():
    """skill 封闭铁律：注册表零缺口——每个动作都有服务端实现。"""
    nofn = [t.name for t in TOOL_REGISTRY if t.fn is None]
    assert not nofn, f"工具缺服务端实现（模型决策面漏到任意代码）：{nofn}"


def test_run_tool_rejects_unknown_and_mismatched():
    """模型只能到注册表：未知工具/坏参数返回失败结果，不执行任何代码。"""

    async def _t():
        ctx = ToolContext(novel_id="n", root_path="/tmp", user_id="u", page="", thread="ch:og")
        r1 = await run_tool(ctx, "__import__('os').system", {})
        assert r1.ok is False
        r2 = await run_tool(ctx, "read_progress", {"not_a_param": 1})
        assert r2.ok is False  # 参数不匹配＝失败结果，非异常外漏

    import asyncio

    asyncio.run(_t())


def test_assistant_modules_have_no_code_execution_surface():
    """assistant/ 全模块源码扫描：无 eval/exec/__import__/compile 调用点
    （白名单外即违规——模型输出永远只被当数据解析）。"""
    offenders: list[str] = []
    for path in sorted(_ASSISTANT_DIR.rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        for i, line in enumerate(src.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for verb in ("eval(", "exec(", "__import__", "compile("):
                if verb not in stripped:
                    continue
                if any(allowed in stripped for allowed in _ALLOWED):
                    continue
                offenders.append(f"{path.name}:{i}: {stripped.strip()[:80]}")
    assert not offenders, f"助手模块出现可执行面（违反 skill 封闭铁律）：{offenders}"
