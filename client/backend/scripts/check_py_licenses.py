#!/usr/bin/env python3
"""依赖许可证门禁（relicense-proprietary）：importlib.metadata 扫当前环境，
三级取值（License-Expression → License → classifier）＋别名归一化＋token 化，
全部命中白名单才绿；OR 任一不在白名单即红（保守方向正确——宁红勿漏）。

⚠️ 本脚本只用于 client-backend-ci.yml 的门禁 step（venv 仅装 requirements.txt）：
本地全量开发 venv（含 pyinstaller/pywebview 等非运行时依赖）跑必红属预期，
严禁复用到 client-package.yml（该工作流把 pyinstaller 装进同一 venv——其
bootloader 按「GPLv2＋Bootloader 例外」随包分发，已在 THIRD-PARTY-NOTICES.txt 列明）。

白名单与 client/frontend/scripts/check-npm-licenses.mjs 同一立场。
首个误红请「补白名单」而非改脚本——补白名单是一次许可评审，改脚本等于拆门禁。
"""
from __future__ import annotations

import re
import sys
from email.message import Message
from importlib import metadata

WHITELIST = {
    "MIT",
    "MIT-0",
    "ISC",
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "BlueOak-1.0.0",
    "CC0-1.0",
    "CC-BY-4.0",
    "MPL-2.0",
    "PSF-2.0",
}

# 常见自由文本/分类器形态 → SPDX 归一化（补表走许可评审，同白名单纪律）
_ALIASES = {
    "mit license": "MIT",
    "apache license 2.0": "Apache-2.0",
    "apache software license": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0",
    "bsd license": "BSD-3-Clause",
    "bsd 3-clause": "BSD-3-Clause",
    "bsd 2-clause": "BSD-2-Clause",
    "isc license": "ISC",
    "python software foundation license": "PSF-2.0",
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    "cc0 1.0 universal (cc0 1.0) public domain dedication": "CC0-1.0",
}

_CLASSIFIER_RE = re.compile(r"^License\s*::\s*OSI Approved\s*::\s*(.+?)\s*$")


def normalize(token: str) -> str:
    t = token.strip()
    low = re.sub(r"\s+", " ", t.lower()).rstrip(".")
    if low in _ALIASES:
        return _ALIASES[low]
    # 分类器缩写（BSD、MIT 等已与 SPDX 同形）；「Python」分类器归 PSF
    if low == "python":
        return "PSF-2.0"
    return t


def extract_licenses(meta: metadata.PackageMetadata) -> list[str]:
    """三级取值：License-Expression（PEP 639）→ License → classifier。"""
    expr = (meta.get("License-Expression") or "").strip()
    if expr:
        return [expr]
    lic = (meta.get("License") or "").strip()
    if lic and lic.upper() != "UNKNOWN":
        # "UNKNOWN" 是 setuptools 旧式缺省占位，不是真实许可（socksio 1.0.0 实锤：
        # License 字段填 UNKNOWN 但同包带 MIT classifier）。按缺省处理落 classifier，
        # 否则占位符短路三级链、真实许可永远读不到；classifier 仍受白名单约束，
        # 保守方向不变。
        # 多行自由文本（PyPI 长描述误填进 License）按段落 token 化前先粗归一
        return [lic]
    for c in meta.get_all("Classifier") or []:
        m = _CLASSIFIER_RE.match(c or "")
        if m:
            return [m.group(1)]
    return []


def parse_tokens(license_str: str) -> list[str]:
    """许可证串 → 归一化 token（AND/OR 分隔，大小写不敏感）。

    Python 生态的自由文本（如 'Apache License, Version 2.0'）含合法逗号，
    不与 npm 同款按逗号切：先整体查别名，再按 AND/OR 切、逐段归一。
    整体与逐段都认不出的 token 原样保留 → 必然白名单外 → 红（保守方向）。
    """
    raw = license_str.strip()
    whole = normalize(raw)
    if whole in WHITELIST:
        return [whole]
    parts = re.split(r"\s+(?:AND|OR)\s+", raw, flags=re.IGNORECASE)
    return [normalize(p) for p in parts if p.strip()]


def check(distributions: dict[str, Message]) -> list[str]:
    violations: list[str] = []
    for name, meta in sorted(distributions.items()):
        lics = extract_licenses(meta)
        if not lics:
            violations.append(f"{name}: license 元数据缺失（三级均无）")
            continue
        bad: list[str] = []
        for lic in lics:
            for token in parse_tokens(lic):
                if token not in WHITELIST:
                    bad.append(token)
        if bad:
            violations.append(f"{name}: {'; '.join(lics)}（白名单外: {', '.join(sorted(set(bad)))}）")
    return violations


def main() -> int:
    dists: dict[str, Message] = {}
    for dist in metadata.distributions():
        name = (dist.metadata.get("Name") or "").strip()
        if not name:
            continue
        dists[name] = dist.metadata
    violations = check(dists)
    if violations:
        print("✗ 依赖许可证门禁未通过——补白名单请走许可评审，勿改本脚本：", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1
    print(f"✓ 依赖许可证门禁通过（{len(dists)} 个发行版全部命中白名单）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
