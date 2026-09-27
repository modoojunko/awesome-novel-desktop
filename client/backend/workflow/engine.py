from fastapi import HTTPException

# 每章版本快照上限：编辑器 1.5s 防抖自动保存每次变更都会写快照，
# 不设上限会随写作时长线性膨胀（读取/列表也跟着变慢）。
MAX_VERSIONS_PER_CHAPTER = 50


def _validate_ref(ref: str) -> str:
    if ".." in ref or "/" in ref:
        raise HTTPException(400, "Invalid chapter reference")
    return ref


def strip_suffix(ref: str, suffix: str = ".yaml") -> str:
    """剥 `.yaml` 尾缀：`vol-1.yaml` → `vol-1`（旧前端调用零断裂，BE-07）。"""
    return ref.removesuffix(suffix)


ALLOWED_TRANSITIONS = {
    "init": ["settings"],
    "settings": ["outline"],
    "outline": ["prompt"],
    "prompt": ["write"],
    "write": ["archive"],
    "archive": ["outline"],
}


def can_transition(current_phase: str, target_phase: str) -> bool:
    return target_phase in ALLOWED_TRANSITIONS.get(current_phase, [])


def update_phase(project, new_phase: str):
    if project.current_phase == new_phase:
        # 幂等：操作类接口（重新生成提示词/重复写入/连建章节）可能已处于目标阶段
        return
    if not can_transition(project.current_phase, new_phase):
        raise ValueError(
            f"Cannot transition from {project.current_phase} to {new_phase}"
        )
    project.current_phase = new_phase


def advance_phase(project, new_phase: str) -> bool:
    """宽容推进（只进不退）：同阶段或合法迁移才置位，非法回退静默跳过返 False。

    操作类接口（建卷、写作工序、润色）的阶段记账统一走这里——操作本身已合法落库，
    阶段标记是「最近一次操作」的记账（novel-workspace 口径），不该被阶段机拖成 500。
    """
    if project.current_phase == new_phase or can_transition(
        project.current_phase, new_phase
    ):
        update_phase(project, new_phase)
        return True
    return False


async def load_chapter(root_path: str, chapter_ref: str) -> dict:
    """DB 心脏（chapters.store）——表⇆JSON 组装；行缺失返回 {}。"""
    from chapters.store import load_chapter as _store_load

    return await _store_load(root_path, chapter_ref)


async def save_chapter(root_path: str, chapter_ref: str, data: dict):
    """统一写入口（chapters.store）：拆装落库 + 元数据派生 + 版本快照。"""
    from chapters.store import save_chapter as _store_save

    await _store_save(root_path, chapter_ref, data)
