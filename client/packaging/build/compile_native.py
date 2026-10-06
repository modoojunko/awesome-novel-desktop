"""把提示词包的关键模块编译成原生扩展（c-prompt-pack-hardening 阶段二）。

为什么：安装包里的 Python 模块是字节码（可反编译）。把「钥匙解封（DPAPI/Keychain）」
「容器解密（AES-GCM）」与「同步器」编译成原生扩展后——
  ① 反编译者读不到这三块逻辑（要逆向二进制）；
  ② 密钥材料与解密参数不落在任何字节码里（钥匙只在原生侧流转）。
这就是用户拍板的阶段二口径（不做云拼装，抬高本机逆向成本）。

只编译这三个模块（不是整个客户端）：

    prompt_pack/localkey.py    钥匙封装/解封
    prompt_pack/container.py   容器 seal/open
    prompt_pack/sync.py        同步器（下载/校验/安装/换档）

`prompt_pack/__init__.py` 保持 Python（只有路径/回执小工具，不含钥匙材料）。

用法（打包链在 PyInstaller **之前**调用）：

    python compile_native.py            # 就地编译（产出 .so/.pyd 与 .py 并存；导入优先取扩展）
    python compile_native.py --scan <dir>   # 扫打包产物：原生扩展必须都在、且没有这三块的字节码/源码

失败即红：编不出来就让打包失败，**不允许**静默回落到字节码版（那等于阶段二没做）。

⚠️ 开发注意：就地编译后 .so 会**遮蔽**同名 .py（导入时扩展优先）——改了这三个模块
必须重跑本脚本，否则改动不生效（症状：测试里新加的函数找不到）。
"""

from __future__ import annotations

import os
import sys

NATIVE_MODULES: tuple[str, ...] = (
    "prompt_pack.localkey",
    "prompt_pack.container",
    "prompt_pack.sync",
)

# 交付包里绝不允许出现的「敏感模块字节码/源码」形态（出现即阶段二被摘掉）
FORBIDDEN_SUFFIXES = (".py", ".pyc", ".pyo")


def _backend_dir() -> str:
    """client/backend（本脚本在 client/packaging/build/ 下）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", "..", "backend"))


def _sources() -> list[tuple[str, str]]:
    backend = _backend_dir()
    out = []
    for mod in NATIVE_MODULES:
        src = os.path.join(backend, *mod.split(".")) + ".py"
        if not os.path.isfile(src):
            raise SystemExit(f"找不到待编译模块：{src}")
        out.append((mod, src))
    return out


def compile_inplace() -> list[str]:
    """就地编译并返回产出的扩展路径（.so/.pyd）。"""
    try:
        from Cython.Build import cythonize
    except ImportError as e:  # pragma: no cover - 打包环境缺依赖时直接失败
        raise SystemExit("缺 Cython——先 `pip install -r client/packaging/build/requirements.txt`") from e
    from setuptools import Extension
    from setuptools.dist import Distribution

    backend = _backend_dir()
    build_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_native")
    os.makedirs(build_dir, exist_ok=True)
    exts = cythonize(
        [Extension(name, [src]) for name, src in _sources()],
        language_level=3,
        build_dir=build_dir,
        quiet=True,
    )
    dist = Distribution({"ext_modules": exts})
    cmd = dist.get_command_obj("build_ext")
    cmd.inplace = True  # 产出与 .py 并存（导入时扩展优先，dev 无扩展则退回 .py）
    cmd.build_lib = backend
    cmd.build_temp = build_dir
    cmd.ensure_finalized()
    # build_ext 的 inplace 目标路径是相对当前工作目录解析的——必须切到 backend 目录再跑，
    # 否则会往仓库根写 prompt_pack/xxx.so（路径不存在 → DistutilsFileError）
    cwd = os.getcwd()
    os.chdir(backend)
    try:
        cmd.run()
    finally:
        os.chdir(cwd)
    made = [os.path.join(backend, *(m.split(".")[:-1]), f"{m.split('.')[-1]}{suf}")
            for m in NATIVE_MODULES
            for suf in _ext_suffixes(backend, m)]
    missing = [m for m in NATIVE_MODULES if not _ext_of(m)]
    if missing:
        raise SystemExit("编译后仍找不到扩展：" + ", ".join(missing))
    _selfcheck(backend)
    return [p for p in made if os.path.exists(p)]


_SELFCHECK = (
    "import os, tempfile;"
    "os.environ['DATA_ROOT'] = tempfile.mkdtemp();"
    "os.environ['AINOVEL_PACK_KEYSTORE'] = 'weak';"
    "import prompt_pack, prompt_pack.container as C, prompt_pack.localkey, prompt_pack.sync;"
    "import prompts;"
    "assert C.backend_name() == 'native', '扩展未生效（仍在用 .py）';"
    "tpl = {'t': 'payload'};"
    "blob = C.seal(tpl, '1');"
    "assert C.open_container(blob, '1') == tpl, 'seal/open 往返不一致';"
    "print('native selfcheck OK', C.__file__)"
)


def _selfcheck(backend: str) -> None:
    """编译后自检：子进程 import 三个模块并跑一次 seal/open 往返。

    只检查「文件存在」不够——损坏的扩展或 ABI 不符（Python 版本对不上）照样会被
    PyInstaller 打进包，扫描闸门也照样过，问题要等用户装完包在解密路径上才炸
    （评审 P2）。这里失败即红。
    """
    import subprocess

    # 用**当前解释器**跑自检：扩展是按本解释器的 ABI 编的，拿 PATH 上的 python 可能对不上
    r = subprocess.run(
        [os.environ.get("PYTHON", sys.executable), "-c", _SELFCHECK],
        cwd=backend,
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        raise SystemExit("原生扩展自检失败（编译产物不可用，禁止进包）：\n" + (r.stdout + r.stderr).strip())


def _ext_suffixes(backend: str, mod: str) -> list[str]:

    pkg_dir = os.path.join(backend, *mod.split(".")[:-1])
    stem = mod.split(".")[-1]
    if not os.path.isdir(pkg_dir):
        return []
    return [n[len(stem):] for n in os.listdir(pkg_dir) if n.startswith(stem) and _is_ext(n)]


def _is_ext(name: str) -> bool:
    import importlib.machinery

    return any(name.endswith(suf) for suf in importlib.machinery.EXTENSION_SUFFIXES)


def _ext_of(mod: str) -> str | None:
    import importlib.machinery

    backend = _backend_dir()
    pkg_dir = os.path.join(backend, *mod.split(".")[:-1])
    stem = mod.split(".")[-1]
    for suf in importlib.machinery.EXTENSION_SUFFIXES:
        p = os.path.join(pkg_dir, stem + suf)
        if os.path.isfile(p):
            return p
    return None


def scan_bundle(root: str) -> list[str]:
    """扫打包产物：返回问题清单（空＝通过）。

    两条不变量（阶段二的门禁）：
      1. 敏感模块必须以**原生扩展**存在（.so/.pyd），缺一即红；
      2. 这三块的 .py/.pyc/.pyo **不得**出现在产物里（出现＝字节码可反编译，等于没编译）。
    """
    problems: list[str] = []
    found_ext: dict[str, str] = {}
    stems = {mod.split(".")[-1]: mod for mod in NATIVE_MODULES}
    for base, _dirs, names in os.walk(root):
        # **只认我们自己的包目录**：依赖里就有同名文件（实测 anthropic/types/container.py、
        # httpcore/_backends/sync.py、sqlalchemy/orm/sync.py）——按裸文件名匹配会在发版时
        # 误报「敏感模块以可反编译形态进包」而打断发布（评审 P1）
        if os.path.basename(base) != "prompt_pack":
            continue
        for n in names:
            p = os.path.join(base, n)
            stem = n.split(".")[0]
            mod = stems.get(stem)
            if mod is None:
                continue
            if _is_ext(n):
                found_ext.setdefault(mod, p)
            elif n == f"{stem}.py" or (n.startswith(f"{stem}.") and n.endswith((".pyc", ".pyo"))):
                problems.append(f"敏感模块以可反编译形态进了产物：{p}")
    for mod in NATIVE_MODULES:
        if mod not in found_ext:
            problems.append(f"产物里缺原生扩展：{mod}（编译步骤被摘掉或未打进包）")
    return problems


def main(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[1] == "--scan":
        problems = scan_bundle(argv[2])
        for p in problems:
            print(f"::error::{p}")
        print("阶段二产物扫描：" + ("通过" if not problems else f"{len(problems)} 处问题"))
        return 0 if not problems else 1
    made = compile_inplace()
    print("编译完成：")
    for p in made:
        print(f"  {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
