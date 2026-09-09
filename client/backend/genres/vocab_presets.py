"""候选源种子（genre-signup-redesign D19）。

稳定 slug 主键（`kind:slug`），**禁止用序号**——序号会随常量顺序漂移，
导致用户已存的 tagId 指向错误标签（不可逆数据损坏）。

前端镜像在 `client/frontend/src/lib/genreVocab.ts`，二者由 parity 测试对拍。
"""

from typing import TypedDict


class VocabEntry(TypedDict):
    id: str
    kind: str
    label: str
    sort: int


def _v(kind: str, slug: str, label: str, sort: int) -> VocabEntry:
    return {"id": f"{kind}:{slug}", "kind": kind, "label": label, "sort": sort}


# ── core_promise 候选（02 主要看什么：enum 起点，可自定义）──────────────
_PROMISE: list[VocabEntry] = [
    _v("promise", "comeback", "以弱破强的痛快", 10),
    _v("promise", "mind-game", "层层反转的智力快感", 20),
    _v("promise", "sweet", "甜到齁的情感满足", 30),
    _v("promise", "survival", "绝处逢生的紧张", 40),
    _v("promise", "scheme", "算无遗策的掌控感", 50),
]

# ── forbidden_list 候选（03 绝对禁止）──────────────────────────────────
_FORBIDDEN: list[VocabEntry] = [
    _v("forbidden", "no-deus-ex-machina", "禁天降外援", 10),
    _v("forbidden", "no-free-powerup", "禁白捡神器", 20),
    _v("forbidden", "no-villain-idiot", "禁反派降智", 30),
    _v("forbidden", "no-foresight", "禁预知破局", 40),
    _v("forbidden", "no-gratuitous-angst", "禁无端虐主", 50),
    _v("forbidden", "no-third-wheel", "禁第三者搅局", 60),
]

# ── battlefield 候选（05 主线战场）─────────────────────────────────────
_BATTLEFIELD: list[VocabEntry] = [
    _v("battlefield", "resources", "抢资源", 10),
    _v("battlefield", "status", "爬地位", 20),
    _v("battlefield", "truth", "查真相", 30),
    _v("battlefield", "affection", "争感情", 40),
    _v("battlefield", "infrastructure", "搞基建", 50),
    _v("battlefield", "external-enemy", "抗外敌", 60),
]

VOCAB_PRESETS: list[VocabEntry] = _PROMISE + _FORBIDDEN + _BATTLEFIELD
