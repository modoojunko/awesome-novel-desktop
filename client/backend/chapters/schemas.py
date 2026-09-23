"""章请求体校验（c-chapter-plan-ai）：路由收裸 dict 的历史口径下，把拆章三列的
闭集/长度校验放在**写入之前**（422），不依赖装配端 _fit 的静默截断。

单源：阶段六档取 volumes/schemas.PLOT_STAGES（与卷纲同源字面）。
"""

from fastapi import HTTPException

from volumes.schemas import PLOT_STAGES

ACTS_MAX_LINES = 4
ACTS_MAX_LEN = 60


def validate_chapter_fields(body: dict) -> None:
    """校验拆章三列（缺键跳过——整表回传以外的局部更新也走这里）。越界 → 422。"""
    if not isinstance(body, dict):
        return
    stage = body.get("plot_stage")
    if stage not in (None, "") and stage not in PLOT_STAGES:
        raise HTTPException(
            422, f"plot_stage 须为固定六档之一：{'/'.join(PLOT_STAGES)}"
        )
    acts = body.get("chapter_acts")
    if acts is None or acts == "":
        return
    lines = acts if isinstance(acts, list) else str(acts).split("\n")
    lines = [str(x) for x in lines if str(x).strip()]
    if len(lines) > ACTS_MAX_LINES:
        raise HTTPException(422, f"chapter_acts 最多 {ACTS_MAX_LINES} 行")
    for ln in lines:
        if len(ln.strip()) > ACTS_MAX_LEN:
            raise HTTPException(422, f"chapter_acts 单行不超过 {ACTS_MAX_LEN} 字")
