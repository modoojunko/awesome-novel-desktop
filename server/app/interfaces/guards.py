"""接口入口的标识参数守卫（s-security-hardening）：把过滤器语法危险形态拦在数据层之前。

两层防线的外层（内层=仓储层字面等值，见 pg_http/client.py 的 RawFilter）：即使未来有人
绕过字面路径，这类输入也到不了查询。规则见 specs/s-query-filter-safety：

- 受守卫参数：订单号 / 权益编号 / 设备标识 / 套餐标识 / 新注册用户名（白名单另见 register_user）；
- 拒绝形态：以查询操作符 token 开头（eq./neq./in./or./not./is./gt./gte./lt./lte./textSearch.），
  或含过滤器语法字符（逗号、圆括号、单双引号）；
- 空值放行（门户预热会发空 pc_hash）；
- 用户名（登录/改密/注销等既有账号路径）**不受守卫**：存量用户名零约束，拦截会锁人——
  其安全性由仓储层字面等值承担；
- 拒绝响应=HTTP 400 + `{code,msg}` 信封（门户拦截器读 data.msg 展示，MUST NOT 只给 detail）。
"""
from __future__ import annotations

from fastapi import Depends, Request

_OPERATOR_PREFIXES = (
    "eq.", "neq.", "gt.", "gte.", "lt.", "lte.", "in.", "is.", "or.", "not.", "textSearch.",
)
_FORBIDDEN_CHARS = (",", "(", ")", '"', "'")

# 参数名 → 用户可读标签（文案口径：只说参数本身，不出现内部术语）
_LABELS = {
    "order_no": "订单号",
    "code_id": "权益编号",
    "pc_hash": "设备标识",
    "sku_key": "套餐标识",
    "challenge": "配对信息",
}


class IdentifierRejected(Exception):
    """标识参数命中危险形态（由全局异常处理器渲染为 {code,msg} 信封）。"""

    def __init__(self, name: str) -> None:
        self.name = name
        self.msg = f"{_LABELS.get(name, name)}格式不正确"
        super().__init__(self.msg)


def is_dangerous_identifier(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    if text.startswith(_OPERATOR_PREFIXES):
        return True
    return any(ch in text for ch in _FORBIDDEN_CHARS)


def guard_identifiers(
    *,
    path: tuple[str, ...] = (),
    query: tuple[str, ...] = (),
    body: tuple[str, ...] = (),
):
    """生成路由级依赖：按名取出 path/query/body 参数并守卫。

    用法（不改端点签名）：`@r.post("/api/xxx", dependencies=[guard_identifiers(body=("order_no",))])`
    """

    async def _guard(request: Request) -> None:
        for name in path:
            if is_dangerous_identifier(request.path_params.get(name, "")):
                raise IdentifierRejected(name)
        for name in query:
            if is_dangerous_identifier(request.query_params.get(name, "")):
                raise IdentifierRejected(name)
        if body:
            try:
                payload = await request.json()
            except Exception:  # noqa: BLE001 — 非 JSON 体交还端点/FastAPI 自行报错
                payload = {}
            if isinstance(payload, dict):
                for name in body:
                    value = payload.get(name)
                    if isinstance(value, str) and is_dangerous_identifier(value):
                        raise IdentifierRejected(name)

    return Depends(_guard)
