# backend/update_channel.py
"""灰度渠道本地覆盖（c-update-staging-channel）。

数据目录下的可选开关文件 `update-channel.yaml`（客户端**只读不写**；不建＝走
生产，行为与历史完全一致，普通用户零感知）：

    # 灰度渠道开关：删掉本文件或改成 prod 即回生产渠道
    channel: staging            # staging=灰度清单 / prod=显式回生产
    update_url: https://…/latest.json   # 高级用法：直指任意清单地址

`channel` 与 `update_url` 同在时 `channel` 优先；`channel` 在场但取值不认识
（如 beta）＝整个覆盖文件不可信，连带 update_url 一起忽略——静默改用另一键
反而制造「我设的没生效」糊涂账。

优先级：覆盖文件 > env（CLIENT_UPDATE_URL / CLIENT_UPDATE_URL_FALLBACK）>
烘焙地址；信任域集合与派生地址由 update_check 按生效候选自动推导，https＋
公网解析出站闸不变。

解析 fail-soft：文件缺失/坏 YAML/空文件/未知取值一律回生产候选链＋warning
日志，绝不 raise——开关文件永远不允许把更新检查弄挂。值容错：utf-8-sig
（记事本 BOM 不致命）、剥标量两侧空白与全角/智能引号（中文输入法手打引号也认）。
"""

import logging
from pathlib import Path

import yaml

from config import DATA_ROOT

logger = logging.getLogger(__name__)

# 灰度清单地址：与 CI 发布侧 download/staging/latest.json 同源；兜底域与客户端
# 烘焙兜底同源（同一 CloudBase env 的静态托管，两域同物）
STAGING_UPDATE_URL = "https://www.awesomenovel.com/download/staging/latest.json"
STAGING_UPDATE_URL_FALLBACK = (
    "https://ai-novel-test-d1ghsr86ra814c12c-1468883265.tcloudbaseapp.com/download/staging/latest.json"
)

# 值两侧要剥的字符：ASCII/全角空白＋直引号＋中日韩弯引号（中文输入法实锤形态）
_STRIP_CHARS = " \t\r\n\f\v\u00a0\u3000\"'“”‘’«»"

_CHANNEL_PATH = Path(DATA_ROOT) / "update-channel.yaml"


def _clean_scalar(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip(_STRIP_CHARS)


def read_override() -> dict:
    """读覆盖文件；任何问题一律返回 {}（＝无覆盖，走生产链）并留 warning。"""
    try:
        raw = _CHANNEL_PATH.read_bytes()
    except OSError:
        return {}
    try:
        data = yaml.safe_load(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        logger.warning("update-channel: %s 解析失败，忽略覆盖（回生产链）：%s",
                       _CHANNEL_PATH.name, exc)
        return {}
    if data is None:  # 全注释/空文件＝无覆盖，不算错
        return {}
    if not isinstance(data, dict):
        logger.warning("update-channel: 覆盖文件不是键值形态（%s），忽略",
                       type(data).__name__)
        return {}
    return data


def override_candidates() -> list[str]:
    """覆盖文件生效时的候选检测地址；空列表＝无覆盖（调用方回落 env/烘焙链）。"""
    ov = read_override()
    if not ov:
        return []
    ch = _clean_scalar(ov.get("channel")).lower()
    if ch == "staging":
        return [STAGING_UPDATE_URL, STAGING_UPDATE_URL_FALLBACK]
    if ch == "prod":
        return []
    if ch:
        logger.warning("update-channel: 未知 channel=%r，覆盖文件整体忽略（回生产链）", ch)
        return []
    url = _clean_scalar(ov.get("update_url"))
    if url:
        return [url]
    logger.warning("update-channel: 覆盖文件无可识别键，忽略（回生产链）")
    return []


def channel_name() -> str:
    """渠道标签（仅反映覆盖文件）：prod / staging / custom。env 覆盖不改变标签。"""
    ov = read_override()
    if not ov:
        return "prod"
    ch = _clean_scalar(ov.get("channel")).lower()
    if ch == "staging":
        return "staging"
    if not ch and _clean_scalar(ov.get("update_url")):
        return "custom"
    return "prod"
