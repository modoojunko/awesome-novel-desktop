# backend/auth_local/service.py
"""浏览器 OAuth 登录 + 30 天滚动验证"""

import base64
import hashlib
import json
import logging
import os
import platform
import subprocess
import urllib.parse
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx

logger = logging.getLogger("auth_local.service")


# 从 config.json 读取 S端 API 地址，避免环境变量传递问题
def _normalize_server_api(base: str) -> str:
    """线上统一走 域名+/api/ 路由：配置裸域名（无路径）时自动补 /api。

    线上域名的路由规则用 /api/ 分流到 S端 后端，调用侧地址必须带该前缀；
    允许显式带自定义子路径的配置（非空 path 一律不改动），只兜裸域名。
    """
    base = base.rstrip("/")
    if base and not urllib.parse.urlsplit(base).path:
        base += "/api"
    return base


def _get_server_api() -> str:
    return _normalize_server_api(
        get_local_config().get("server_api", "")
        or os.environ.get("SERVER_API_BASE")
        or "https://your-cloudbase-app.com/api"
    )


def _get_public_server_api() -> str:
    """宿主可访问的 S端 API 地址（前端打开授权页用）；默认与 SERVER_API_BASE 一致"""
    return _normalize_server_api(
        get_local_config().get("public_server_api", "")
        or os.environ.get("PUBLIC_SERVER_API")
        or _get_server_api()
    )


def _build_auth_url(public_api: str, pc_hash: str, pc_name: str, device_profile: str) -> str:
    """授权页地址：由 S端 前端 /auth 唯一承载（后端内联页已删除）。

    从 API 基址剥掉 /api 得 web origin；配置为自定义子路径（无 /api 后缀）
    时保持原样——该形态下宿主域名本就没有 SPA，属配置约束。
    device_profile 为 URL-safe Base64（无 padding），query 可原样拼接。
    """
    web_origin = public_api.rstrip("/").removesuffix("/api")
    return (
        f"{web_origin}/auth"
        f"?pc_hash={pc_hash}"
        f"&pc_name={urllib.parse.quote(pc_name)}"
        f"&device_profile={device_profile}"
    )


def _get_server_api_fallback() -> str:
    """S端 兜底基址：自定义域名解析抖动时 call_server_api 自动切直连。

    取值链：config.json.server_api_fallback → env SERVER_API_FALLBACK /
    AI_NOVEL_SERVER_API_FALLBACK → 空（无兜底，行为同旧版单基址）。
    """
    return _normalize_server_api(
        get_local_config().get("server_api_fallback", "")
        or os.environ.get("SERVER_API_FALLBACK")
        or os.environ.get("AI_NOVEL_SERVER_API_FALLBACK")
        or ""
    )


CONFIG_DIR = str(Path(os.environ.get("DATA_ROOT", "data")).resolve())
CONFIG_FILE = str(Path(CONFIG_DIR) / "config.json")
SESSION_DAYS = 30
POLL_INTERVAL = 2
POLL_TIMEOUT = 120

# 档位兜底名单（仅"无快照"分支使用，见 check_permission 分支 4）：
# 含归一化档位 pro/max 与历史档位名——兜老 S端 与首次升级未刷新的窗口
# （c-s-entitlement-sync：主判定路径不存在档位白名单，快照优先）。
FALLBACK_MEMBER_TIERS = ("trial", "pro", "max",
                         "monthly", "quarterly", "yearly", "lifetime")

# 快照完整性：features 是 list 且 limits.max_projects 键存在（Q3 三段式的判定前提）
def _snapshot_complete(ent) -> bool:
    return (
        isinstance(ent, dict)
        and isinstance(ent.get("features"), list)
        and isinstance(ent.get("limits"), dict)
        and "max_projects" in ent["limits"]
    )


# 档位标准配置镜像（与 docs/contracts/entitlement-defaults.json 同源，tests 对拍；
# 只用于"快照存在但不完整且重同步不可得"的极端分支——按档位标准给权限，不是瞎放开）
_TIER_ALIAS = {"monthly": "pro", "quarterly": "pro", "yearly": "pro", "lifetime": "pro"}
STANDARD_FALLBACK = {
    "none":  {"features": [], "limits": {"max_projects": 1}},
    "free":  {"features": [], "limits": {"max_projects": 1}},
    "trial": {"features": ["settings-ai-fields", "outline-advanced-fields",
                           "ai-generate", "prompt-panel", "ai-model"],
              "limits": {"max_projects": None}},
    "pro":   {"features": ["settings-ai-fields", "outline-advanced-fields",
                           "ai-generate", "prompt-panel", "ai-model"],
              "limits": {"max_projects": None}},
    "max":   {"features": ["settings-ai-fields", "outline-advanced-fields",
                           "ai-generate", "prompt-panel", "ai-model"],
              "limits": {"max_projects": None}},
}


def standard_fallback_for(tier: str) -> dict:
    return STANDARD_FALLBACK.get(_TIER_ALIAS.get(tier, tier), STANDARD_FALLBACK["none"])


# 重同步节流：快照不完整时 async 门禁边界触发，60s 内不重复打 S端
_LAST_ENT_RESYNC = {"t": 0.0}

# S端 门户（购买/续费/开通试用入口），可通过 config.json 覆盖
DEFAULT_PORTAL_URL = "https://novel-s-web-ai-novel-test-d1ghsr86ra814c12c.webapps.tcloudbase.com"


def get_local_config() -> dict:
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except OSError:
        pass
    return {}


def save_local_config(config: dict):
    Path(CONFIG_DIR).mkdir(parents=True, exist_ok=True)
    Path(CONFIG_FILE).write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_or_create_config() -> dict:
    cfg = get_local_config()
    changed = False
    defaults = {
        "pc_hash": "",
        "pc_name": "",
        "api_key": "",
        "api_base_url": "https://api.deepseek.com/anthropic",
        "api_model": "deepseek-v4-flash",
        "token": "",
        "username": "",
        "tier": "none",
        "expires_at": "",
        "last_login_at": "",
        "server_api": "",
        "portal_url": DEFAULT_PORTAL_URL,
        "deletion_pending": False,
        "entitlement": None,
    }
    for k, v in defaults.items():
        if k not in cfg:
            cfg[k] = v
            changed = True
    if not cfg.get("pc_hash"):
        cfg["pc_hash"] = generate_pc_hash()
        cfg["pc_name"] = platform.node() or "My PC"
        changed = True
    # 环境变量中的 SERVER_API_BASE 同步到 config.json（持久化）
    if os.environ.get("SERVER_API_BASE") and not cfg.get("server_api"):
        cfg["server_api"] = os.environ["SERVER_API_BASE"]
        changed = True
    if changed:
        save_local_config(cfg)
    return cfg


def generate_pc_hash() -> str:
    info = []
    try:
        for wmic_query in [
            "cpu get ProcessorId",
            "baseboard get SerialNumber",
            "diskdrive get SerialNumber",
        ]:
            try:
                result = subprocess.run(
                    ["wmic"] + wmic_query.split(),
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if result.returncode == 0:
                    lines = result.stdout.strip().split("\n")
                    if len(lines) > 1:
                        val = lines[1].strip()
                        if val:
                            info.append(val)
            except OSError:
                continue
    except OSError:
        pass
    if not info:
        try:
            info.append(platform.node() or "")
            result = subprocess.run(
                ["wmic", "os", "get", "SerialNumber"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                if len(lines) > 1:
                    info.append(lines[1].strip())
        except OSError:
            pass
    raw = "-".join(info) or platform.node() or "unknown"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def collect_device_profile() -> dict:
    """采集当前设备硬件信息，构造 DeviceProfile"""
    info = []
    for wmic_query in [
        "cpu get ProcessorId",
        "baseboard get SerialNumber",
        "diskdrive get SerialNumber",
    ]:
        try:
            result = subprocess.run(
                ["wmic"] + wmic_query.split(),
                capture_output=True, text=True, timeout=5, check=False
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                if len(lines) > 1:
                    val = lines[1].strip()
                    if val:
                        info.append(val)
        except (OSError, subprocess.TimeoutExpired):
            continue

    raw = "-".join(info) or platform.node() or "unknown"
    fingerprint = hashlib.sha256(raw.encode()).hexdigest()

    return {
        "fingerprint": fingerprint,
        "hostname": platform.node() or "",
        "os": platform.platform() or "",
        "os_arch": platform.machine() or "",
    }


def encode_device_profile(device_info: dict) -> str:
    """DeviceProfile → URL-safe Base64（无 padding）"""
    payload = {
        "f": device_info.get("fingerprint", ""),
        "h": device_info.get("hostname", ""),
        "o": device_info.get("os", ""),
        "a": device_info.get("os_arch", ""),
    }
    raw = json.dumps(payload, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


async def call_server_api(
    endpoint: str,
    method: str = "GET",
    params: dict | None = None,
    json_body: dict | None = None,
) -> dict:
    # 主基址失败（自定义域名解析抖动/超时）自动切兜底基址，终端用户零感知
    bases = list(
        dict.fromkeys(
            b for b in (_get_server_api(), _get_server_api_fallback()) if b
        )
    )
    last_err_msg = "S端 不可达"
    for base in bases:
        url = f"{base}/{endpoint}"
        try:
            # 60s：云托管 MinNum=0 缩容后首次请求需冷启动（30-60s），10s 会误报超时
            async with httpx.AsyncClient(timeout=60) as client:
                if method == "GET":
                    resp = await client.get(url, params=params)
                else:
                    resp = await client.post(url, json=json_body)
                try:
                    return resp.json()
                except ValueError:
                    # 云托管网关冷启动/重启期间可能返回空体或 HTML 错误页
                    return {"code": -1, "msg": f"S端响应异常（HTTP {resp.status_code}）"}
        except httpx.TimeoutException:
            last_err_msg = "网络超时"
            logger.warning("event=s_api_call_timeout base=%s endpoint=%s", base, endpoint)
        except httpx.RequestError as e:
            last_err_msg = f"网络错误: {e!s}"
            logger.warning("event=s_api_call_error base=%s endpoint=%s error=%s", base, endpoint, e)
    return {"code": -1, "msg": last_err_msg}


async def browser_auth(silent: bool = False) -> dict:
    """打开系统浏览器让用户在 S端 登录，后台轮询授权结果

    silent=True 时只静默检测是否已授权，不打开浏览器、不轮询
    """
    cfg = load_or_create_config()
    pc_hash = cfg["pc_hash"]

    # 静默模式：只查一次，不打开浏览器
    if silent:
        result = await call_server_api("check-auth", params={"pc_hash": pc_hash})
        if result.get("code") == -1:
            # S端 不可达（云托管缩容冷启动 503 / 网络断）：区别于「未登录」，
            # 前端 useAuthHeal 据此识别为可重试而非直接放弃
            return {"code": -1, "msg": result.get("msg", "S端 不可达")}
        if result.get("code") == 0:
            data = result["data"]
            cfg["token"] = data["token"]
            cfg["username"] = data.get("username", "")
            cfg["tier"] = data.get("tier", "none")
            cfg["expires_at"] = data.get("expires_at", "")
            cfg["entitlement"] = data.get("entitlement")   # 权益快照（entitlement-sync）
            cfg["entitlement_fetched_at"] = datetime.now(UTC).isoformat()
            cfg["last_login_at"] = datetime.now(UTC).isoformat()
            cfg["deletion_pending"] = False  # 重新登录/撤销恢复：清除暂停标记
            save_local_config(cfg)
            await _ensure_local_user(cfg["username"])
            return {
                "code": 0,
                "data": {
                    "message": "已登录",
                    "tier": cfg["tier"],
                    "token": cfg["token"],
                },
            }
        if result.get("code") == 2:
            # 注销撤销期（account-deletion）：付费与套餐功能暂停；凭据保留（可撤销恢复），
            # 结构化信号交由前端提示，不触发登出。暂停落地为本地权限标记，
            # check_permission() 读取后 allowed=False（AI/会员能力冻结，撤销即恢复）。
            data = result.get("data", {})
            cfg["deletion_pending"] = True
            save_local_config(cfg)
            return {
                "code": 2,
                "data": {
                    "deletion_pending": True,
                    "days_left": data.get("days_left", 0),
                    "deadline": data.get("deadline", ""),
                    "message": "账号注销申请处理中，付费与套餐功能已暂停；可到网页控制台撤销。本地作品不受影响。",
                },
            }
        if result.get("code") == 1:
            # S端 明确「未登录/会话失效」：曾登录过（config.json 有 token）说明会话已被
            # 服务端作废（典型=账号已注销/会话丢失）——清凭据并发结构化失效信号（design D6）。
            # 本地 SQLite 作品数据全程不触碰。
            if cfg.get("token"):
                deleted = bool((result.get("data") or {}).get("deleted"))
                stale_user = cfg.get("username", "")
                for k in ("token", "username", "expires_at", "last_login_at",
                          "entitlement_fetched_at"):
                    cfg[k] = ""
                cfg["tier"] = "none"
                cfg["entitlement"] = None
                cfg["deletion_pending"] = False
                save_local_config(cfg)
                logger.info("event=session.invalidated user=%s deleted=%s", stale_user, deleted)
                return {
                    "code": 1,
                    "data": {
                        "session_invalid": True,
                        "deleted": deleted,
                        "message": "登录状态已失效（账号可能已注销）。你设备上的作品仍完好保留。",
                    },
                }
            return {"code": 1, "data": {"message": "未登录"}}
        # 兜底：未知 code 按未登录处理（保持旧行为）

    # 采集设备信息并编码为 device_profile
    device_info = collect_device_profile()
    device_profile = encode_device_profile(device_info)

    # 构造授权页 URL（宿主可访问地址，由前端在宿主浏览器打开）
    pc_name = cfg.get("pc_name", "")
    auth_url = _build_auth_url(_get_public_server_api(), pc_hash, pc_name, device_profile)
    return {"code": 1, "data": {"auth_url": auth_url, "message": "请在浏览器中完成登录"}}


async def verify_session() -> dict:
    """验证 30 天会话，返回套餐和剩余试用天数"""
    cfg = load_or_create_config()
    token = cfg.get("token", "")
    last_login = cfg.get("last_login_at", "")
    expires_at = cfg.get("expires_at", "")

    if not token:
        return {"valid": False, "msg": "未登录"}

    try:
        login_time = datetime.fromisoformat(last_login) if last_login else None
        if login_time and login_time.tzinfo is None:
            login_time = login_time.replace(tzinfo=UTC)
        if login_time and datetime.now(UTC) - login_time > timedelta(days=SESSION_DAYS):
            return {"valid": False, "msg": f"登录已超过 {SESSION_DAYS} 天，请重新登录"}
    except ValueError:
        return {"valid": False, "msg": "登录信息异常"}

    if login_time and datetime.now(UTC) < login_time:
        return {"valid": False, "msg": "系统时间异常"}

    # 套餐判定统一走 check_permission（tier/is_member/expired/project_limit/剩余天数）
    perm = check_permission()
    resp = {
        "valid": True,
        "tier": perm["tier"],
        "is_member": perm.get("is_member", False),
        "expired": perm.get("expired", False),
        "expires_at": expires_at,
        "project_limit": perm.get("project_limit"),
        "trial_remaining_days": perm.get("trial_remaining_days", 0),
        "entitlement_degraded": perm.get("entitlement_degraded", False),
    }
    if perm.get("entitlement") is not None:
        resp["entitlement"] = perm["entitlement"]  # 快照原文（无快照省略）
    return resp


def _perm(tier: str, *, allowed: bool = True, is_member: bool = False,
          expired: bool = False, reason: str = "", msg: str = "",
          project_limit: int | None = 1, trial_remaining_days: int = 0,
          degraded: bool = False, entitlement: dict | None = None) -> dict:
    """check_permission 统一返回形状（新增 entitlement/entitlement_degraded 两个键）。"""
    d: dict = {
        "allowed": allowed,
        "tier": tier,
        "is_member": is_member,
        "expired": expired,
        "project_limit": project_limit,
        "trial_remaining_days": trial_remaining_days,
        "entitlement_degraded": degraded,
    }
    if entitlement is not None:
        d["entitlement"] = entitlement
    if reason:
        d["reason"] = reason
    if msg:
        d["msg"] = msg
    return d


def check_permission(now: date | None = None) -> dict:
    """检查当前用户套餐权限（c-s-entitlement-sync 快照驱动口径）

    判定优先级链（spec tier-access / entitlement-sync）：
    0) deletion_pending → 免费基线
    1) 免费档位 → 免费基线；trial 无到期生产收紧（与过期同口径），
       env ENTITLEMENT_LEGACY_TRIAL=1 保留旧宽限（仅 dev/test 注入）
    2) 本地过期/非法 → 免费基线（先于快照，快照可能更陈旧）
    3) 完整快照自证：is_member = features 非空或 max_projects 不限；
       project_limit = limits.max_projects（None=不限）
       快照存在但不完整 → 档位标准兜底 STANDARD_FALLBACK + degraded=True
       （重同步由 async 边界 ensure_entitlement_snapshot 负责，本函数零网络 IO）
    4) 无快照（老 S端 / 未刷新）→ FALLBACK_MEMBER_TIERS 档位兜底

    allowed 保留旧语义（False 仅出现在暂停/过期/信息异常），workflow.tier_bypass 据此旁路。
    """
    cfg = get_local_config()
    tier = cfg.get("tier", "none") or "none"
    expires_at = cfg.get("expires_at", "")
    now = now or datetime.now(UTC).date()
    ent = cfg.get("entitlement")

    def _remaining_days() -> int:
        if not expires_at:
            return 0
        try:
            return max(0, (date.fromisoformat(expires_at[:10]) - now).days)
        except ValueError:
            return 0

    # 0) 注销撤销期（account-deletion）：付费与套餐功能暂停；撤销后重新登录自动清除。
    if cfg.get("deletion_pending"):
        return _perm(tier, allowed=False, reason="deletion_pending",
                     msg="账号注销申请处理中，付费与套餐功能已暂停；可到网页控制台撤销。本地作品不受影响。",
                     trial_remaining_days=_remaining_days())

    # 1) 免费档位 / trial 无到期收紧
    if tier not in FALLBACK_MEMBER_TIERS:
        return _perm(tier, trial_remaining_days=_remaining_days())
    if (tier == "trial" and not expires_at
            and not os.environ.get("ENTITLEMENT_LEGACY_TRIAL")):
        return _perm(tier, allowed=False, expired=True, reason="trial_no_expiry",
                     msg="试用信息异常，已降为免费待遇 — 开通套餐或联系客服恢复",
                     trial_remaining_days=0)

    # 2) 到期检查（lifetime 永不过期；无到期数据对付费档保留旧兼容）
    if tier != "lifetime" and expires_at:
        try:
            if date.fromisoformat(expires_at[:10]) < now:
                return _perm(tier, allowed=False, expired=True, reason="expired",
                             msg="套餐已过期，已降为免费待遇 — 续费后恢复全部功能",
                             trial_remaining_days=0)
        except ValueError:
            return _perm(tier, allowed=False, expired=True, reason="invalid",
                         msg="套餐信息异常",
                         trial_remaining_days=0)

    # 3) 快照优先
    if _snapshot_complete(ent):
        features = ent["features"]
        max_projects = ent["limits"]["max_projects"]
        is_member = bool(features) or max_projects is None
        return _perm(tier, is_member=is_member, project_limit=max_projects,
                     trial_remaining_days=_remaining_days(), entitlement=ent)
    if ent is not None:
        # 快照存在但不完整：重同步（async 边界）仍不可得 → 按档位标准兜底 + 降级标志
        fb = standard_fallback_for(tier)
        is_member = bool(fb["features"]) or fb["limits"]["max_projects"] is None
        return _perm(tier, is_member=is_member,
                     project_limit=fb["limits"]["max_projects"],
                     trial_remaining_days=_remaining_days(), degraded=True)

    # 4) 无快照兜底（老 S端 / 未刷新）：档位名单判定
    return _perm(tier, is_member=True, project_limit=None,
                 trial_remaining_days=_remaining_days())


async def ensure_entitlement_snapshot() -> None:
    """快照三段式第一段（Q3）：本地快照存在但不完整时，静默重同步一次。

    只允许在 async 边界调用（deps 门禁 / 端点）——check_permission 保持同步纯读。
    60s 节流：离线等重同步不可得场景不逐请求打 S端。
    """
    import time as _time

    ent = get_local_config().get("entitlement")
    if ent is None or _snapshot_complete(ent):
        return
    now = _time.monotonic()
    if now - _LAST_ENT_RESYNC["t"] < 60:
        return
    _LAST_ENT_RESYNC["t"] = now
    try:
        await browser_auth(silent=True)  # code 0 即覆盖快照；其余码维持现状
    except Exception:  # noqa: BLE001 重同步失败不阻断门禁，走兜底
        logger.warning("event=entitlement_resync_failed")


async def _ensure_local_user(username: str) -> None:
    """Ensure the OAuth-authenticated S端 user exists in C端's local DB."""
    if not username:
        return
    try:
        from db import async_session
        from models.user import User

        async with async_session() as session:
            from sqlalchemy import select

            existing = await session.execute(select(User).where(User.id == username))
            if not existing.scalar_one_or_none():
                session.add(
                    User(
                        id=username,
                        email=f"{username}@s.local",
                        password_hash="*",
                        display_name=username,
                    )
                )
                await session.commit()
    except Exception:  # noqa: S110
        pass
