"""卷族 Pydantic 校验 — 四档长度纪律的唯一执行点。

SQLite 不强制 VARCHAR 长度；这里 max_length 真校验（422）：
标签/枚举 50；一句话 150；标题 200；短段落 300。
plants/reveals 契约是 list[str]（一行一条）：normalize_line_list 归一
（换行归一、逐行 strip、丢空行）＋ 逐行 ≤150 ＋ 行数上限；该归一函数导出供
volumes/render.py 装配端复用（校验与装配同一语义，禁止两套）。
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# 剧情节点阶段（固定六档，storyline 卷视图）
PLOT_STAGES = ["开局铺垫", "冲突初现", "矛盾升级", "重要转折", "高潮爆发", "卷末收束"]

# 一行一条字段的行数上限（防单 TEXT 列被灌爆）
LINE_LIST_MAX_LINES = 200
LINE_MAX = 150


def normalize_line_list(value: list[str]) -> list[str]:
    """一行一条字段的归一：换行统一为 \\n、逐行 strip、丢空行。"""
    out: list[str] = []
    for item in value:
        for line in str(item).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            line = line.strip()
            if line:
                out.append(line)
    return out


# ── 卷纲子项 ────────────────────────────────────────────────────────────────


class CastMemberIn(BaseModel):
    """本卷登场人物行：角色 + 本卷目标 + 预期变化。"""

    who: str = Field(max_length=50)
    target: str = Field(default="", max_length=150)
    change: str = Field(default="", max_length=150)


class PlotNodeIn(BaseModel):
    """本卷关键剧情节点行：阶段（固定六档）＋ 节点内容与结果。"""

    stage: str = Field(max_length=50)
    text: str = Field(default="", max_length=300)

    @field_validator("stage")
    @classmethod
    def _stage_enum(cls, v: str) -> str:
        if v not in PLOT_STAGES:
            raise ValueError(f"stage 须为固定六档之一：{'/'.join(PLOT_STAGES)}")
        return v


# ── 卷本体 ──────────────────────────────────────────────────────────────────


class VolumeCreate(BaseModel):
    """建卷（统一入口）：四问可选直写＋章数——抽卡确认与免费「直接创建」共用（一次写入）。"""

    title: str = Field(default="", max_length=200)
    summary: str = Field(default="", max_length=300)
    core_conflict: str = Field(default="", max_length=150)
    ending: str = Field(default="", max_length=300)
    antagonist_type: str | None = Field(default=None, max_length=20)
    antagonist_line: str = Field(default="", max_length=150)
    chapter_target: int | None = Field(default=None, ge=1, le=9999)

    @field_validator("antagonist_type")
    @classmethod
    def _ant_enum(cls, v: str | None) -> str | None:
        if not v:
            return v
        if v not in ("人物", "难题", "环境", "自我", "势力"):
            raise ValueError("antagonist_type 须为闭集之一：人物/难题/环境/自我/势力")
        return v


class VolumeUpdate(BaseModel):
    """PUT /volumes/{ref} — 全字段可选，只更新显式传入的键。

    清空通道：标量与一行一条字段以 model_fields_set 判定——请求体里显式携带
    `"chapter_target": null` / `"plants": []` 即清空（service 层据 fields_set 写入）。
    """

    model_config = ConfigDict(extra="ignore")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=300)
    core_conflict: str | None = Field(default=None, max_length=150)
    ending: str | None = Field(default=None, max_length=300)
    chapter_target: int | None = Field(default=None, ge=1, le=9999)
    # 本卷的坎（c-volume-antagonist）
    antagonist_type: str | None = Field(default=None, max_length=20)
    antagonist_line: str | None = Field(default=None, max_length=150)
    # 行集整体替换（传入即全量重写该族，未传不动）
    plot_nodes: list[PlotNodeIn] | None = None

    # 退役键（c-volume-antagonist）：显式携带＝422——静默 ignore 会让调用方误以为写入
    # 成功（评审拍板：六键硬拒，其余未知键维持 ignore）
    @model_validator(mode="before")
    @classmethod
    def _retired_reject(cls, data):
        if isinstance(data, dict):
            hit = [k for k in ("template_name", "plan_line", "goal", "plants",
                               "reveals", "cast_members") if k in data]
            if hit:
                raise ValueError(f"字段已退役（c-volume-antagonist）：{','.join(hit)}——伏笔请走台账接口")
        return data

    @field_validator("antagonist_type")
    @classmethod
    def _ant_type_enum(cls, v: str | None) -> str | None:
        if not v:
            return v
        if v not in ("人物", "难题", "环境", "自我", "势力"):
            raise ValueError("antagonist_type 须为闭集之一：人物/难题/环境/自我/势力")
        return v
