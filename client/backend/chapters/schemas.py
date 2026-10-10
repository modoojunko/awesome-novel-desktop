"""章请求体校验（c-chapter-plan-ai）：路由收裸 dict 的历史口径下，把章级闭集/长度
校验放在**写入之前**（422），不依赖装配端 _fit 的静默截断。

单源：阶段六档取 volumes/schemas.PLOT_STAGES（与卷纲同源字面）。

c-og-slim-v2：「本章行动」校验随该列退役；剧情条目新增非字符串项拒收。
"""

from fastapi import HTTPException

from volumes.schemas import PLOT_STAGES

# 章内剧情条目预算（c-plot-split）：存储预算——单条 ≤200 字、≤12 条。
# 校验与装配同一语义（normalize_plot_items 导出供 store 复用，禁止两套——
# 照 volumes/schemas.normalize_line_list 先例）；生成预算另计（端点层）。
PLOT_MAX_ITEMS = 12
PLOT_MAX_LEN = 200


_SENT_ENDS = "。！？；…"


def clip_sentence(text, limit: int) -> str:
    """句读点截断工具（c-field-truncation-alignment）：超预算截到最后一个句读点。
    终版口径下内容字段已改完整直通、生产链不再调用；本工具保留供自检/导出等
    可选场景（chapters/ai_plot.clip_plot_item 委托此处）。"""
    t = str(text or "").strip()
    if len(t) <= limit:
        return t
    cut = t[:limit]
    for i in range(len(cut) - 1, -1, -1):
        if cut[i] in _SENT_ENDS:
            return cut[: i + 1]
    return cut


def normalize_plot_items(items: list) -> list[str]:
    """剧情条目归一：只收字符串项（非字符串丢弃＝防御性兜底，请求层已 422 拒收）＋
    截 12 条（计数预算保留）；**单条不截**（c-field-truncation-alignment 终版：内容
    完整引入提示词）；含换行的条目单条完整保留。

    越界只夹不报错——保存链不产生错误、自动保存不被冻结（spec：越界内容只在
    输入侧硬夹，服务端夹是防御性兜底）。

    c-og-slim-v2：**禁 str() 兜底**——把对象条目字符串化成 `{'text': ...}` 会
    静默落库并计入正文提示词（输入收口的动机）。
    """
    out: list[str] = []
    for item in items[:PLOT_MAX_ITEMS]:
        if not isinstance(item, str):
            continue
        out.append(item)
    return out


def validate_chapter_fields(body: dict) -> None:
    """校验章级写入字段（缺键跳过——整表回传以外的局部更新也走这里）。越界 → 422。

    接受两套键名：章档案口径（`plot_stage`，整表回传）与拆章卡面口径（`stage`，
    排上请求体）——两处落的是同一列，校验必须在**两条路都生效**。
    """
    if not isinstance(body, dict):
        return
    stage = body.get("plot_stage", body.get("stage"))
    if stage not in (None, "") and stage not in PLOT_STAGES:
        raise HTTPException(
            422, f"阶段只能是：{'/'.join(PLOT_STAGES)}"
        )
    # 章内剧情条目（c-plot-split / c-og-slim-v2）：形状＝字符串数组（非数组 422）；
    # **非字符串项一律拒收**（对象/数组/数字会让整条被字符串化后落库并进提示词）。
    # 预算越界就地静默夹（normalize_plot_items）——超长/超条数不产生保存错误，更不进
    # ogFormIssues 类整表问题清单（issues 非空会连坐冻结自动保存＝数据丢失路径）。
    # 缺键/None 跳过（落库 presence-gate 保持现值，见 store._disassemble_scalars）。
    if "plot_items" in body and body.get("plot_items") is not None:
        items = body.get("plot_items")
        if not isinstance(items, list):
            raise HTTPException(422, "剧情条目必须是字符串数组（一条一段场景描述）")
        if any(not isinstance(x, str) for x in items):
            raise HTTPException(422, "剧情条目只能是字符串（一条一段场景描述）")
        body["plot_items"] = normalize_plot_items(items)
