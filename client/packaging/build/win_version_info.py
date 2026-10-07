"""Windows 版本资源生成单源（c-nuitka-full）：exe 文件属性里的「发布者」「公司」等。

为什么抽出来：build.spec（PyInstaller）与 build_nuitka.py（Nuitka）双引擎都需要
version_info.txt——生成逻辑两份手抄必然漂移（bundle_manifest 同款教训）。build.spec
在 spec 执行期调用；build.bat 的 Nuitka 分支／build_nuitka 在打包前调用。

口径（与 build.bat / CI 安装包同源）：
- 品牌字段全部取自 brand/brand.json（与两端前端同源，唯一声明处，勿在此写死）；
  缺键/非串/空白串一律显式失败，不静默出「未知发布者」的包。
- 版本：环境变量 APP_VERSION > git describe > 0.0.0（CI 在 Build app 步骤注入
  github.ref_name；本地 build.bat 已 set 同名变量）。
- 仅 Windows 生成并使用；macOS 返回 None 不生成文件（mac 侧主体元数据另行立项）。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

_INTERNAL_NAME = "AwesomeNovel"


def _brand_field(brand: dict, key: str) -> str:
    v = brand.get(key)
    if not isinstance(v, str) or not v.strip():
        raise SystemExit(
            f"brand/brand.json 缺有效字符串字段 {key}（经营主体/品牌署名需要）——补齐后再构建"
        )
    return v.strip()


def _detect_version(root_dir: Path) -> str:
    v = os.environ.get("APP_VERSION", "").strip()
    if not v:
        try:
            r = subprocess.run(
                ["git", "describe", "--tags", "--always", "--dirty"],
                capture_output=True, text=True, cwd=str(root_dir))
            v = r.stdout.strip() if r.returncode == 0 else ""
        except OSError:
            v = ""
    v = v[1:] if v.startswith("v") else v  # tag 去 v 前缀
    # 清洗进字符串字段（提交哈希/斜杠等不进元数据），数字位由 match 另取
    return re.sub(r"[^A-Za-z0-9.+_-]", "-", v) or "0.0.0"


def collect(root_dir: Path) -> dict | None:
    """收集版本资源字段（仅 win32）；非 Windows 返回 None。

    返回 dict：publisher/brand_name/brand_name_en/ver/file_version（点分数字串，
    最多四段，可直接喂 Nuitka --file-version/--product-version——它们只收数字
    不收 VSVersionInfo 文件，c-nuitka-full 演练判例）。
    """
    if sys.platform != "win32":
        return None

    brand = json.loads((root_dir / "brand" / "brand.json").read_text(encoding="utf-8"))
    publisher = _brand_field(brand, "company")
    brand_name = _brand_field(brand, "name")
    brand_name_en = _brand_field(brand, "nameEn")

    ver = _detect_version(root_dir)
    # 数字版本位只取首个点分数字前缀（四段各为 16 位 WORD）：
    # describe 尾巴（提交哈希/PR 号等）不进数字位，超段 clamp 0–65535
    prefix = re.match(r"\d+(?:\.\d+)*", ver)
    segs = [min(int(seg), 65535) for seg in (prefix.group(0).split(".") if prefix else [])]
    nums = tuple((segs + [0, 0, 0, 0])[:4])
    return {
        "publisher": publisher,
        "brand_name": brand_name,
        "brand_name_en": brand_name_en,
        "ver": ver,
        "file_version": ".".join(str(n) for n in nums),
    }


def write_version_file(spec_dir: Path, root_dir: Path) -> Path | None:
    """生成 version_info.txt（PyInstaller 引擎用；Nuitka 走 collect() 离散旗标）。"""
    if sys.platform != "win32":
        return None

    fields = collect(root_dir)
    assert fields is not None
    publisher = fields["publisher"]
    brand_name = fields["brand_name"]
    ver = fields["ver"]
    nums = tuple(int(x) for x in fields["file_version"].split("."))
    file_desc = f"{brand_name} ({fields['brand_name_en']})"
    copyright_line = f"© {publisher}"

    version_file = spec_dir / "version_info.txt"
    # 模板用 !r 生成合法字面量——值含引号/反斜杠也不炸加载器 eval，勿改回裸插值
    version_file.write_text(f"""# -*- coding: utf-8 -*-
# 由 win_version_info.py 自动生成——勿手改、勿提交
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={nums},
    prodvers={nums},
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
    date=(0, 0, 0, 0)),
  kids=[
    StringFileInfo([
      StringTable(
        '080404b0',
        [StringStruct('CompanyName', {publisher!r}),
         StringStruct('FileDescription', {file_desc!r}),
         StringStruct('FileVersion', {ver!r}),
         StringStruct('InternalName', {_INTERNAL_NAME!r}),
         StringStruct('LegalCopyright', {copyright_line!r}),
         StringStruct('OriginalFilename', {_INTERNAL_NAME + '.exe'!r}),
         StringStruct('ProductName', {brand_name!r}),
         StringStruct('ProductVersion', {ver!r})])
      ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
""", encoding="utf-8")
    return version_file
