"""章请求体校验（c-chapter-plan-ai）：路由收裸 dict 的历史口径下，把拆章三列的
闭集/长度校验放在**写入之前**（422），不依赖装配端 _fit 的静默截断。

单源：阶段六档取 volumes/schemas.PLOT_STAGES（与卷纲同源字面）。
"""

from fastapi import HTTPException

from volumes.schemas import PLOT_STAGES

ACTS_MAX_LINES = 4
ACTS_MAX_LEN = 60

# 章内剧情条目预算（c-plot-split）：存储预算——单条 ≤200 字、≤12 条。
# 校验与装配同一语义（normalize_plot_items 导出供 store 复用，禁止两套——
# 照 volumes/schemas.normalize_line_list 先例）；生成预算另计（端点层）。
PLOT_MAX_ITEMS = 12
PLOT_MAX_LEN = 200


def normalize_plot_items(items: list) -> list[str]:
    """剧情条目归一：逐条 str 化＋单条截 200＋截 12 条；含换行的条目单条完整保留。

    越界只夹不报错——保存链不产生错误、自动保存不被冻结（spec：越界内容只在
    输入侧硬夹，服务端夹是防御性兜底）。
    """
    out: list[str] = []
    for item in items[:PLOT_MAX_ITEMS]:
        s = item if isinstance(item, str) else str(item)
        out.append(s[:PLOT_MAX_LEN])
    return out


def validate_chapter_fields(body: dict) -> None:
    """校验拆章三列（缺键跳过——整表回传以外的局部更新也走这里）。越界 → 422。

    接受两套键名：章档案口径（`plot_stage`/`chapter_acts`，整表回传）与
    拆章卡面口径（`stage`/`acts`，排上请求体）——两处落的是同一列，
    校验必须在**两条路都生效**（排上路径曾因只认前者而成为死代码）。
    """
    if not isinstance(body, dict):
        return
    stage = body.get("plot_stage", body.get("stage"))
    if stage not in (None, "") and stage not in PLOT_STAGES:
        raise HTTPException(
            422, f"阶段只能是：{'/'.join(PLOT_STAGES)}"
        )
    # 章内剧情条目（c-plot-split）：形状＝字符串数组（非数组才 422）；预算越界
    # 就地静默夹（normalize_plot_items）——超长/超条数不产生保存错误，更不进
    # ogFormIssues 类整表问题清单（issues 非空会连坐冻结自动保存＝数据丢失路径）。
    # 缺键/None 跳过（落库 presence-gate 保持现值，见 store._disassemble_scalars）。
    if "plot_items" in body and body.get("plot_items") is not None:
        items = body.get("plot_items")
        if not isinstance(items, list):
            raise HTTPException(422, "剧情条目必须是字符串数组（一条一段场景描述）")
        body["plot_items"] = normalize_plot_items(items)
    acts = body.get("chapter_acts", body.get("acts"))
    if acts is None or acts == "":
        return
    lines = acts if isinstance(acts, list) else str(acts).split("\n")
    lines = [str(x) for x in lines if str(x).strip()]
    if len(lines) > ACTS_MAX_LINES:
        raise HTTPException(422, f"本章行动最多 {ACTS_MAX_LINES} 行（一行一个动作）")
    for ln in lines:
        if len(ln.strip()) > ACTS_MAX_LEN:
            raise HTTPException(422, f"本章行动单行不超过 {ACTS_MAX_LEN} 字")
