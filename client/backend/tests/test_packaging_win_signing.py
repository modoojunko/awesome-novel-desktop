"""Windows 代码签名门禁：签名链路（证书解析 → 签 exe → iscc → 校验）必须保持完整。

背景（2026-10-06）：用户双击安装包看到「Windows 已保护你的电脑 / 发布者: 未知」——
SmartScreen 对**未签名**安装包的判定，唯一解法是 Authenticode 代码签名（证书从公共
CA 买 / Azure Trusted Signing）。签名链路已落地，但打包流水线只在推 tag 时跑
（PR 不编译 .iss，2026-10-02 省额度拍板），链路被改丢不会有任何运行时测试变红，
故在此钉死四条不变量：

1. `installer.iss` 的 SignTool 指令必须包在 `#ifdef SignToolScript` 里——不传 define
   （没证书的构建）时编译结果必须与历史逐字一致，签名不能变成出包的前置条件；
2. `sign_win.ps1` 必须是唯一签名入口，且支持文档里承诺的四类调用与环境变量；
3. 程序本体必须在 **Inno 打包前**签名（打完包再签外面那份＝用户装出来的仍是未签名件）；
4. 配了证书却没签上（证书过期/时间戳不通）必须硬失败——校验闸门不许被摘掉。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CERT_DIR = Path(__file__).resolve().parents[2] / "packaging" / "cert"
BUILD_DIR = Path(__file__).resolve().parents[2] / "packaging" / "build"
REPO_ROOT = BUILD_DIR.parents[2]
INSTALLER_ISS = BUILD_DIR / "installer.iss"
SIGN_SCRIPT = BUILD_DIR / "sign_win.ps1"
BUILD_RELEASE = BUILD_DIR / "build_release.ps1"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "client-package.yml"


def _active_lines(text: str) -> list[tuple[int, str]]:
    """去掉 Inno 注释行（`;` 起头）与空行，返回 (行号, 内容) 的活跃指令行。"""
    lines = []
    for no, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith(";"):
            continue
        lines.append((no, stripped))
    return lines


def test_signtool_directive_is_optional():
    """SignTool 必须在 #ifdef 里：没证书的构建不许被签名拦下，也不许被悄悄改行为。"""
    text = INSTALLER_ISS.read_text(encoding="utf-8")
    assert "#ifdef SignToolScript" in text, "缺 #ifdef SignToolScript 守卫"
    # 按守卫块切三段（本文件另有 MyAppVersion 的 #ifndef/#endif，不能按第一个 #endif 切）
    before, rest = text.split("#ifdef SignToolScript", 1)
    guarded, after = rest.split("#endif", 1)

    active = [line for _no, line in _active_lines(guarded) if line.startswith("SignTool=")]
    assert active, "守卫块里没有 SignTool= 指令——签名链路被摘掉了"
    assert "SignedUninstaller=yes" in guarded, (
        "缺 SignedUninstaller=yes——卸载器会退回「未知发布者」（UAC 会提示）"
    )
    assert "$f" in active[0], "SignTool 命令必须带 $f（Inno 用它替换待签文件路径）"

    # 守卫之外不得再出现活跃的 SignTool 指令（否则没证书的构建也会去调用签名工具）
    offenders = [
        (no, line)
        for no, line in _active_lines(before + after)
        if line.startswith(("SignTool=", "SignedUninstaller="))
    ]
    assert not offenders, (
        "SignTool/SignedUninstaller 出现在 #ifdef 守卫之外——无证书构建会被强绑签名：\n"
        + "\n".join(f"  L{no}: {line}" for no, line in offenders)
    )


def test_sign_script_is_the_single_entry():
    """签名入口唯一：四类动作 + 文档承诺的环境变量名都在，后续才能「加证书＝配两个变量」。"""
    text = SIGN_SCRIPT.read_text(encoding="utf-8")
    for action in ("Sign", "Verify", "IsccArgs", "Resolve"):
        assert f"'{action}'" in text, f"sign_win.ps1 缺动作 {action}"
    for env in (
        "AINOVEL_SIGN_PFX",
        "AINOVEL_SIGN_PFX_PASSWORD",
        "AINOVEL_SIGN_THUMBPRINT",
        "AINOVEL_SIGN_DEV_CERT",
        "AINOVEL_SIGN_TIMESTAMP_URL",
        # 2023-06 起公共 CA 只发「硬件保护、不可导出」的证书 → 云签名走 /dlib 是主线形态，
        # 这两个环境变量是「买到证书就能接上」的关键，不能少
        "AINOVEL_SIGN_DLIB",
        "AINOVEL_SIGN_DMDF",
    ):
        assert env in text, f"sign_win.ps1 不认环境变量 {env}（文档里承诺过）"
    assert "/dlib" in text and "/dmdf" in text, "缺云签名（HSM / Trusted Signing）的 signtool 参数"
    assert "signtool" in text.lower(), "缺 signtool 调用"
    assert "/tr" in text or "-tr" in text, "缺 RFC3161 时间戳参数——证书过期后旧安装包会失去签名效力"
    assert "Get-AuthenticodeSignature" in text, "缺签名校验（Verify 动作）"


def test_app_exe_is_signed_before_packaging():
    """程序本体必须在 Inno 打包**前**签：打包后再签外面那份，安装出来的仍是未签名件。"""
    text = BUILD_RELEASE.read_text(encoding="utf-8")
    sign_pos = text.find("程序本体签名")
    iscc_pos = text.find("Inno Setup 安装包")
    assert sign_pos != -1, "build_release.ps1 缺程序本体签名步骤"
    assert iscc_pos != -1, "build_release.ps1 缺 Inno 打包步骤"
    assert sign_pos < iscc_pos, "签名步骤须排在 Inno 打包之前"
    assert "dist\\AwesomeNovel\\AwesomeNovel.exe" in text, "签名目标不是程序本体 exe"
    assert "IsccArgs" in text and "Verify" in text, (
        "build_release.ps1 缺 iscc 签名参数传递或出包后校验"
    )
    # 内测一键自签（-DevSign）：让导入过根证书的机器看到发布者名而不是「发布者未知」，别被改丢
    assert "[switch]$DevSign" in text, "build_release.ps1 缺 -DevSign 开关"
    assert "AINOVEL_SIGN_DEV_CERT" in text, "-DevSign 没接到自签证书环境变量上"


def test_ci_pipeline_order_and_verification_gate():
    """CI：证书准备 → 签 exe → iscc（带签名参数）→ 校验闸门，顺序与闸门缺一不可。"""
    wf = WORKFLOW.read_text(encoding="utf-8")
    order = [
        "Configure Windows code signing",
        "Sign app exe (Windows)",
        "Build Windows installer",
        "Verify installer signature (Windows)",
    ]
    positions = []
    for name in order:
        pos = wf.find(name)
        assert pos != -1, f"client-package.yml 缺步骤：{name}"
        positions.append(pos)
    assert positions == sorted(positions), (
        "签名步骤顺序错了（证书准备 → 签 exe → 打包 → 校验）：" + str(positions)
    )
    assert "WINDOWS_SIGN_PFX" in wf, "CI 缺证书 secret 入口"
    assert "IsccArgs" in wf, "iscc 没带签名参数——安装器与卸载器不会签名"
    assert "AwesomeNovel.exe" in wf, "CI 没签程序本体"
    assert "::warning" in wf and "未签名构建" in wf, (
        "没配证书时必须打 warning——否则「以为签了其实没签」只有用户能发现"
    )


def test_dev_cert_matches_documented_password_and_brand():
    """内测自签证书可加载、密码与安装脚本/签名脚本同值、CN 是新品牌名。

    （改名后旧证书 CN=AI Novel，签出来的「签署者」还是旧名——此断言防它重演。）"""
    from cryptography.hazmat.primitives.serialization import pkcs12

    pfx = CERT_DIR / "cert.pfx"
    assert pfx.is_file(), f"缺内测自签证书：{pfx}"
    key, cert, _extra = pkcs12.load_key_and_certificates(pfx.read_bytes(), b"ainovel123")
    assert key is not None and cert is not None, "cert.pfx 无法用文档密码解出私钥/证书"
    assert "Awesome Novel" in cert.subject.rfc4514_string(), (
        f"自签证书 CN 不是新品牌名：{cert.subject.rfc4514_string()}（改名前的旧名会签出旧签署者）"
    )
    for path in (CERT_DIR / "install_cert.bat", CERT_DIR / "install_cert.ps1", SIGN_SCRIPT):
        assert "ainovel123" in path.read_text(encoding="utf-8"), (
            f"{path.name} 里的证书密码与 cert.pfx 不一致"
        )


def test_signing_doc_reachable_from_offline_packaging_doc():
    """离线打包文档必须指到签名文档：内测同学从那条入口进来，不能只看到「属预期」。"""
    offline = (REPO_ROOT / "docs" / "ops" / "client-package-offline-windows.md").read_text(
        encoding="utf-8"
    )
    assert "client-code-signing.md" in offline, "离线打包文档缺签名文档链接"
    signing = REPO_ROOT / "docs" / "ops" / "client-code-signing.md"
    assert signing.is_file(), f"缺签名文档：{signing}"
    doc = signing.read_text(encoding="utf-8")
    for token in ("SmartScreen", "WINDOWS_SIGN_PFX", "Unblock-File", "自签"):
        assert token in doc, f"签名文档缺关键内容：{token}"


def test_no_stale_unsigned_claims():
    """不得再出现「CI 本来就不签名」这类过期口径（它会让内测以为提示无解）。"""
    for path in (BUILD_RELEASE, WORKFLOW):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"CI\s*同样不签名", text), f"{path.name} 残留「CI 同样不签名」口径"


def test_powershell_scripts_parse():
    """打包 PowerShell 脚本必须能被解析（本机无 pwsh 则跳过；CI 的 ubuntu runner 自带）。

    2026-10-06 实锤：sign_win.ps1 在**命令参数位**用多行 `+` 拼接被判成语法错误——脚本一
    被调用就整段挂掉（本地与 CI 的签名步骤全废），而这种错误只有解析器能抓，且只能靠
    pwsh 跑。上面那些静态门禁全是字符串匹配，抓不到语法。"""
    import shutil
    import subprocess

    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("pwsh 不可用——本机未装 PowerShell（CI 上会执行）")
    parse = (
        "$e=$null;"
        "[System.Management.Automation.Language.Parser]::ParseFile("
        "'{path}',[ref]$null,[ref]$e)|Out-Null;"
        "if ($e.Count) {{ $e | ForEach-Object {{ $_.Message }}; exit 1 }}"
    )
    for script in (SIGN_SCRIPT, BUILD_RELEASE):
        result = subprocess.run(
            [pwsh, "-NoProfile", "-Command", parse.format(path=script)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"{script.name} 解析失败：{result.stdout.strip()} {result.stderr.strip()}"
        )
