# backend/outbound_guard.py
"""出站 URL 校验单源（c-proxy-fakeip-compat）。

四条 CDN/更新链路（update_check×2／prompt_pack sync／kb baseline／kb tree）原本各自
持有 `_validate_outbound` 拷贝且规则微差（kb 带 http+环回开发逃生口、trusted 空集语义
相反）；本模块收敛为单源，逐字保持各自语义。规则两段：

  1) 目标段：https（`allow_dev_loopback` 时额外放行 http＋环回宿主的开发形态）＋可信域；
  2) 解析段：DNS 解析结果判定 verdict——
       ok      全部为公网 IP；
       fakeip  全部落在 198.18.0.0/15（TUN 型代理 fake-ip DNS 的指纹；该段是 RFC2544
               benchmark 保留段，不可路由到任何内网服务，放行不破坏 SSRF/DNS-rebinding
               防护语义——连接照常发起，由代理按域名转发）；
       blocked 其余（含 fake-ip 混真实公网/非公网地址的混合解析）。

放行 ⇔ verdict ∈ {ok, fakeip}（blocked 一律拒）。返回 (放行, verdict)，调用方据
verdict 细分失败原因（fake-ip 环境下的获取失败记 proxy_fake_ip，与普通 cdn_unreachable
可区分）。kb 开发逃生口（宿主为 127.0.0.1/localhost 时跳过解析段公网闸）语义保持。
"""

import ipaddress
import socket
from urllib.parse import urlparse

# clash 系 TUN 缺省 fake-ip-range（RFC 2544 benchmark 保留段）
FAKEIP_NET = ipaddress.ip_network("198.18.0.0/15")
LOOPBACK_HOSTS = ("127.0.0.1", "localhost")


def classify_infos(infos) -> str:
    """解析结果 → verdict：ok（全公网）／fakeip（全在 fake-ip 段）／blocked（其余）。

    混合解析（fake-ip 混任一公网或非公网地址）一律 blocked——全命中才是 TUN fake-ip
    的唯一指纹，混合是 DNS rebinding 的现实形态，保守取交集。
    """
    saw_global = saw_fakeip = False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return "blocked"
        if ip.is_global:
            saw_global = True
        elif ip in FAKEIP_NET:
            saw_fakeip = True
        else:
            return "blocked"
    if saw_global and saw_fakeip:
        return "blocked"
    if saw_fakeip:
        return "fakeip"
    if saw_global:
        return "ok"
    return "blocked"


def validate_outbound(
    url: str,
    trusted_hosts: set[str] | frozenset[str],
    *,
    allow_dev_loopback: bool = False,
    trusted_required: bool = True,
    resolve=None,
) -> tuple[bool, str]:
    """sync 全量校验 → (是否放行, verdict)。

    allow_dev_loopback：kb 两链的开发逃生口——http＋环回宿主放行进域校验，且宿主为
    环回字面量时跳过解析段公网闸（旧语义逐字保持）。trusted_required：kb tree 的
    「可信域空集直接拒」语义（baseline 是空集放行）。
    """
    try:
        p = urlparse(url)
        host = (p.hostname or "").lower()
        loopback_host = host in LOOPBACK_HOSTS
        if p.scheme == "https":
            pass
        elif allow_dev_loopback and p.scheme == "http" and loopback_host:
            pass  # 本地测试
        else:
            return False, "blocked"
        if trusted_required and not trusted_hosts:
            return False, "blocked"
        if trusted_hosts and host not in trusted_hosts:
            return False, "blocked"
        # 宿主本身是 IP 字面量的情况：非公网直接拒（环回宿主走逃生口）
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        if literal is not None and not literal.is_global and not (allow_dev_loopback and loopback_host):
            return False, "blocked"
        if resolve is None:
            infos = socket.getaddrinfo(p.hostname, 443, proto=socket.IPPROTO_TCP)
        else:
            infos = resolve(p.hostname)
    except (OSError, ValueError):
        return False, "blocked"
    if allow_dev_loopback and loopback_host:
        return True, "ok"
    verdict = classify_infos(infos)
    return (verdict != "blocked", verdict)
