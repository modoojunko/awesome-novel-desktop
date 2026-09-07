"""C端 OAuth 授权流：auth-page / authorize / check-auth。"""
from __future__ import annotations

import logging

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse

from app.application.devices.authorize_device import authorize_device
from app.infrastructure.repositories.factory import (
    code_repo,
    device_repo,
    grant_repo,
    user_repo,
)
from app.interfaces.deps import Db, get_db
from app.interfaces.dto import AuthorizeRequest

logger = logging.getLogger("api.client.auth")

AUTH_PAGE_HTML = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>爱小说 · 设备授权</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei","Noto Sans SC",sans-serif;background:#fdf8f3;color:#3d352a;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.card{background:#fff;max-width:400px;width:100%;padding:32px;border-radius:12px;border:1px solid #e5d5c0;box-shadow:0 1px 3px rgba(0,0,0,0.06)}
.logo{display:flex;align-items:center;gap:8px;margin-bottom:24px}
.logo-icon{width:32px;height:32px;border-radius:8px;background:linear-gradient(135deg,#d4a574,#a67c52);display:flex;align-items:center;justify-content:center;color:#fff;font-size:16px;font-family:"EB Garamond","Noto Serif SC",serif;font-weight:700}
h1{font-family:"EB Garamond","Noto Serif SC",serif;font-size:20px;font-weight:700;margin:0}
p.sub{color:#8b7355;font-size:14px;margin-bottom:24px;line-height:1.5}
label{display:block;font-size:14px;font-weight:500;margin-bottom:4px;color:#3d352a}
input{width:100%;padding:10px 14px;font-size:14px;border:1px solid #e5d5c0;border-radius:8px;background:#fff;color:#3d352a;outline:none;transition:border-color .15s;margin-bottom:16px}
input:focus{border-color:#8b6914}
button{width:100%;padding:12px;font-size:15px;font-weight:500;background:#8b6914;color:#faf6ee;border:none;border-radius:8px;cursor:pointer;transition:background .15s}
button:hover{background:#7a5d12}
button:disabled{opacity:.5;cursor:not-allowed}
.error{color:#b85a5a;font-size:13px;display:none;margin-top:12px;padding:10px 14px;background:rgba(184,90,90,.1);border-radius:8px}
.success{display:none;text-align:center;padding:20px 0}
.success-icon{width:64px;height:64px;color:#5a8a5a;margin:0 auto 16px;display:block}
.success h2{font-family:"EB Garamond","Noto Serif SC",serif;font-size:20px;font-weight:700;margin-bottom:8px}
.success p{color:#8b7355;font-size:14px}
</style>
</head>
<body>
<div class="card" id="card">
<div class="logo"><div class="logo-icon">&#9998;</div><h1>爱小说</h1></div>
<div id="formView">
<p class="sub">桌面应用请求绑定此设备，请登录以完成授权</p>
<form id="authForm">
<input type="hidden" name="pc_hash" id="pc_hash">
<input type="hidden" name="device_profile" id="device_profile">
<label for="username">用户名</label><input type="text" name="username" id="username" required>
<label for="password">密码</label><input type="password" name="password" id="password" required>
<button type="submit" id="submitBtn">授权登录</button>
<p class="error" id="errorMsg"></p>
</form>
</div>
<div class="success" id="successView">
<svg class="success-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
<h2>授权成功</h2>
<p>此页面可以关闭了</p>
</div>
</div>
<script>
document.getElementById('authForm').addEventListener('submit', async function(e){
  e.preventDefault();var btn=document.getElementById('submitBtn');btn.disabled=true;btn.textContent='授权中...';
  var params=new URLSearchParams(window.location.search);
  document.getElementById('pc_hash').value=params.get('pc_hash')||'';
  document.getElementById('device_profile').value=params.get('device_profile')||'';
  try{
    var resp=await fetch('/api/authorize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      username:document.getElementById('username').value,
      password:document.getElementById('password').value,
      pc_hash:document.getElementById('pc_hash').value,
      device_profile:document.getElementById('device_profile').value
    })});
    var data=await resp.json();
    if(data.code===0){
      document.getElementById('formView').style.display='none';
      document.getElementById('successView').style.display='block';
    }else{
      var err=document.getElementById('errorMsg');
      err.style.display='block';err.textContent=data.msg||'授权失败';
      btn.disabled=false;btn.textContent='授权登录';
    }
  }catch(e){
    var err=document.getElementById('errorMsg');
    err.style.display='block';err.textContent='网络错误，请重试';
    btn.disabled=false;btn.textContent='授权登录';
  }
});
</script>
</body>
</html>"""

from app.interfaces.client_api.router import router as r


@r.get("/api/auth-page")
async def api_auth_page(request: Request):
    """返回授权页面（C端 OAuth 流程）。"""
    return HTMLResponse(AUTH_PAGE_HTML)


@r.post("/api/authorize")
async def api_authorize(
    req: AuthorizeRequest,
    db: Db = Depends(get_db),
):
    logger.info("event=authorize.start user=%s", req.username)
    result = authorize_device(
        user_repo(db), code_repo(db), device_repo(db), grant_repo(db),
        username=req.username.strip(),
        password=req.password,
        pc_hash=req.pc_hash,
        pc_name=req.pc_name,
        device_profile_b64=req.device_profile,
    )
    logger.info("event=authorize.result user=%s code=%d", req.username, result["code"])
    if result["code"] == 0:
        db.commit()
    return result


@r.get("/api/check-auth")
async def api_check_auth(pc_hash: str = "", db: Db = Depends(get_db)):
    """C端 轮询：该 pc_hash 是否已授权。"""
    if not pc_hash:
        return {"code": 1, "msg": "缺少 pc_hash"}
    try:
        grant = grant_repo(db).get(pc_hash)
        if grant:
            from datetime import datetime, timedelta, timezone

            from app.domain.identity.deletion import is_due, remaining_days
            from app.domain.licensing import License
            from app.infrastructure.repositories.factory import user_repo
            from app.infrastructure.repositories.payments_repo import OrderRepo

            # 注销门禁（account-deletion）：撤销期付费功能暂停（code 2）；已注销拒绝
            # （执行时 device_grants 已清空，此分支为补偿扫描先行标记的兜底）
            user = user_repo(db).get(grant.username)
            if user and user.is_deleted():
                return {"code": 1, "msg": "该账号已注销", "data": {"deleted": True}}
            if user and user.is_deletion_pending():
                if user.deletion_deadline and is_due(user.deletion_deadline):
                    from app.application.identity.deletion_service import (
                        execute_due_deletions,
                    )
                    execute_due_deletions(
                        user_repo(db), code_repo(db), device_repo(db), grant_repo(db),
                        usernames=[grant.username],
                    )
                    return {"code": 1, "msg": "该账号已注销", "data": {"deleted": True}}
                return {
                    "code": 2,
                    "msg": "账号注销进行中",
                    "data": {
                        "deletion_pending": True,
                        "days_left": remaining_days(user.deletion_deadline) if user.deletion_deadline else 0,
                        "deadline": user.deletion_deadline.isoformat() if user.deletion_deadline else "",
                    },
                }

            codes = code_repo(db).find_active_by_username(grant.username)
            license_ = License(username=grant.username).merge(codes)

            data = {
                "token": grant.token,
                "username": grant.username,
                "tier": license_.effective_tier,
                "expires_at": license_.max_expires_at.isoformat() if license_.max_expires_at else "",
            }

            # ── 权益快照（c-s-entitlement-sync，契约 v1）：档位目录配置 →
            #    ENTITLEMENT_DEFAULTS 兜底（档位行缺配置/坏 JSON/未知档位）；
            #    免费基线 = 空 features + max_projects=1。排队/冻结/收回语义由
            #    License.merge 继承，快照随下次 check-auth 自动反映。──
            from app.config import settings as _settings
            from app.infrastructure.repositories.payments_repo import TierRepo

            tier_cfg = TierRepo(db).find_entitlement_by_key(license_.effective_tier)
            ent = tier_cfg or _settings.ENTITLEMENT_DEFAULTS.get(
                license_.effective_tier, _settings.ENTITLEMENT_DEFAULTS["none"])
            data["entitlement"] = {"v": 1, **ent}

            # ── A4 扩展（可选字段，无支付数据时省略）──
            # days_remaining：北京自然日口径（今日 0 点到 expires_at，floor）；无套餐/免费省略
            if license_.max_expires_at:
                tier = license_.effective_tier
                if tier not in ("none", "free"):
                    bj_tz = timezone(timedelta(hours=8))
                    expires_bj = license_.max_expires_at.astimezone(bj_tz)
                    today0_bj = datetime.now(bj_tz).replace(
                        hour=0, minute=0, second=0, microsecond=0)
                    days = (expires_bj - today0_bj).days
                    days = max(days, 0)
                    data["days_remaining"] = days

            # attention：账号动态（退款进行中含冷静期 / 冻结待核对）
            uid = user_repo(db).get_id(grant.username)
            if uid:
                flags = OrderRepo(db).attention_flags(uid)
                if flags["refund_processing"] or flags["verify_pending"]:
                    data["attention"] = flags

            return {"code": 0, "data": data}
        return {"code": 1, "msg": "等待授权"}
    except Exception:
        logger.exception("event=check_auth_error pc_hash=%s", pc_hash)
        return {"code": -1, "msg": "内部错误，请查看服务器日志"}
