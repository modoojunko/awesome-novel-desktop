from fastapi import APIRouter

router = APIRouter(tags=["web"])


# 各子路由模块持有自己的 APIRouter，在此显式 include。
# 勿改回「模块内 from router import r 装饰器注册」的副作用写法——那依赖
# import 副作用，ruff 会把"未使用"的模块 import 当死代码删掉，路由随之
# 失挂（/api/web/login 等门户路由 404 事故，ruff --fix 84 项 reintroduce）。
from app.interfaces.web_api.account import r as account_router
from app.interfaces.web_api.cron import r as cron_router
from app.interfaces.web_api.dev_inject import r as dev_router
from app.interfaces.web_api.devices import r as devices_router
from app.interfaces.web_api.notify import r as notify_router
from app.interfaces.web_api.payments import r as pay_router

router.include_router(account_router)
router.include_router(devices_router)
router.include_router(pay_router)
router.include_router(dev_router)
router.include_router(cron_router)
router.include_router(notify_router)
# web_api/license.py（/api/license/activate 激活码端点）已随 8.3 拆除——
# 购买流程统一走 /api/pay/orders；管理端发码面已撤（s-code-issue：发码走本地脚本）
