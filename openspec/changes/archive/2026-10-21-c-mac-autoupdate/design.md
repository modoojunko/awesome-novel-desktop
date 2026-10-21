# Design — c-mac-autoupdate

## 病灶与决策（2026-10-21 勘察实锤）

| 环节 | 现状 | 本变更 |
| --- | --- | --- |
| `build.spec` BUNDLE | 无 `info_plist` → PyInstaller 默认 0.0.0 | 传入版本（`win_version_info.detect_version` 单源） |
| `update_check._PLATFORM_KEY` | `{"win32": "win"}` | 加 `darwin → "mac"`（发布链 latest.json 的键名） |
| 壳层 apply 平台闸 | `!= "win32"` 一票否决 | win32 → PS runner（原样）；darwin → bash runner；其余忽略 |
| 发布侧 | `platforms.mac` 早已必产（DMG url/sha256/size） | 零改动 |
| 前端三态横幅 | 零平台分叉 | 零改动 |

## macOS runner 形态（与 Windows PS runner 同构）

```
detached: /bin/bash -c "<script>"  (start_new_session)
  1. 等父进程死透：kill -0 轮询，有界 60s，超时放行（与 Windows 同判据）
  2. hdiutil attach -nobrowse -readonly -noautoopen -mountpoint <mkdtemp>
  3. 挂载点根 glob *.app → ditto 复制到 <bundle>.update（同卷，保元数据/软链）
  4. codesign --verify --strict <暂存 bundle>  —— 硬闸，失败不碰既有 bundle
  5. mv <bundle> <bundle>.old-<pid> && mv <bundle>.update <bundle>（同目录 rename 原子）
     失败回滚：.old 挪回
  6. rm -rf <bundle>.old-*；hdiutil detach（尽力而为）
  7. pending.relaunch 为真 → open <bundle>（安装成功才拉起）
  8. installer-runner.log 一行留痕：wait_s / parent_alive_after_wait / install 结果 / install_seconds / relaunched
```

关键判据：
- **执行体在安装目录之外**＝/bin/bash（系统自带），bundle 换装自锁不存在；脚本全文经
  argv 下发不落盘（「暂不」清理名单无需扩）。
- **安装目录钉死**＝`sys.executable` 上溯三级解析当前 .app（PyInstaller onedir 形态
  `X.app/Contents/MacOS/X`）；bundle 结构解析不出（dev 态）→ 静默跳过。
- **换装原子性**：staging 与目标同目录（rename 原子）；旧 bundle 挪 `.old` 后立刻换入，
  失败即回滚——不存在「两份都没有」窗口（rename 间隔微秒级，进程已死透无占用）。
- **权限预检在退出链**（探针实测 `.app` 父目录可写，复用 `_install_dir_writable` 判据）：
  非 admin 装到 /Applications 的不可写形态在 spawn 前跳过，不留下半次换装。
- **无 quarantine 面**：DMG 由 httpx 自下（无 LSFileQuarantineEnabled 的下载器才写
  quarantine xattr），挂载产物不带隔离属性，`open` 不触发 Gatekeeper 首启评估。
- **共享段零改动**：TTL 10 分钟／重试上限 2／sha256 完整复验（闸前）/pending 唯一属主/
  `_reconcile_pending` 启动对拍记账——全部平台无关。

## bundle 版本注入

- `win_version_info._detect_version` → 公开 `detect_version`（`collect` 内部同源）；
  build.spec 在 darwin 分支以同一函数取版本传 `BUNDLE(info_plist={...})`。
- `build_mac.sh` 已算 `APP_VERSION`，补 `export` 即与 CI 同名变量同源。
- CI 断言（`client-package.yml` mac 段，codesign 前）：`/usr/lib/PlistBuddy -c 'Print'
  对拍 `${GITHUB_REF_NAME#v}` 清洗值——v030 判例「断言进打包链」。

## 风险与边界

- **Gatekeeper**：产物本就带真证书签名（CI Codesign app 步），换装不改变信任形态；
  `codesign --verify --strict` 只做完整性校验（ad-hoc 本地构建同样过）。
- **同名改名安装**：目标名取当前 bundle 名（用户改过名的安装位不破）。
- **磁盘**：DMG 只读挂载不占额外空间，复制峰值 ≈ .app 体积。
- **失败可见性**：全部失败路径留痕 installer-runner.log（「暂不」清理保留名单既有），
  横幅回落手动链。
