# c-relaunch-version-selfreport · 任务

## 1. 影响判定

- [x] 1.1 界面影响判定：无 React 屏改动、无应用内文案（进程环境与版本自报），
      依据 proposal「Design Impact」免原型先行；在 change 目录记录判定结论。

## 2. 壳层（client/packaging/build/pywebview_app.py）

- [x] 2.1 `_env_with_release` 冻结分支：frozen 判别式（与 get_install_dir 同式）
      下 `os.environ[name] = release.get(key) or fallback` 强制覆盖后 return；
      非 frozen 原两段补缺逻辑不变。验证：源码形状断言（frozen 分支串在场）。
- [x] 2.2 main() boot 版本行：`client_version_at_boot` frozen 下不读
      `os.environ["CLIENT_VERSION"]`（直接烘焙值，缺省 dev）。验证：形状断言。
- [x] 2.3 `_BAKED_ENV_KEYS` 常量＋`_without_baked_env(env) -> dict`（拷贝剔除，
      其余原样，空 dict 安全）；mac spawn env dict 过滤、Windows spawn 补
      `env=_without_baked_env(os.environ)`。验证：helper 三臂直测＋两平台接线
      形状断言。

## 3. 测试（client/backend/tests/test_packaging_shell_apply.py）

- [x] 3.1 `_without_baked_env` 三臂：含 7 baked 键＋PATH 的假 env → baked 全剥、
      PATH 保留；空 dict → 空 dict；返回 dict 为新对象（不改入参）。
- [x] 3.2 形状断言：`_env_with_release` frozen 强制覆盖行、boot 行 frozen 判别、
      mac `_without_baked_env(os.environ)`、Windows `env=_without_baked_env(`
      各串在场；存量用例保绿不改钉。

## 4. 回归

- [x] 4.1 后端全量：`python -m pytest tests/ -q --timeout=30`（CI 同口径）退出码 0，
      记录通过数。
- [x] 4.2 门禁结论登记：未触前端四门不涉；ruff 闸内全绿；壳层 A/B 对拍无新增账；
      落 change 目录 verification.md。

## 5. 发版与真机验收（v0.43.1 同车）

- [ ] 5.1 Windows 灰度跳（0.42/0.43→0.43.1）：新实例徽章与 `update-check.current`
      报 0.43.1（若 0.43 时徽章曾停 0.42，此跳即 Windows 同病的治疗实证）。
- [ ] 5.2 macOS 灰度跳（0.43→0.43.1）：runner `open` 拉起的新实例 startup.log
      shell main 行 `version=0.43.1`（不再 0.43）＋徽章 0.43.1＋置前/左上角不回归。
- [x] 5.3 OpenSpec 归档随实现 PR：sync client-auto-update ADDED delta 到主 spec，
      change 移入 archive，`openspec validate --strict` 通过并记录。
