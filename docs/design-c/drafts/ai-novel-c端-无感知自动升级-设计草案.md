# ai-novel C端 无感知自动升级 · 设计草案

> 2026-10-13 起草 · 未立项。回答一个问题：**现在升级要用户自己去官网下载安装包再跑一遍
> 安装器，怎么把「程序面」的升级做到一次点击完成，同时不碰「数据面」的知情同意链。**
>
> **主流程已拍板（2026-10-13）**：后台下载 → 后台就位 → 就绪通知 → 用户点「重启更新」→
> 完成更新。不自动安装生效、不自动重启；用户唯一动作是点一下。
>
> **v3（同日）：经双路架构评审（运行时侧＋打包发布侧）修订**——9 条 P1/8 条 P2 已闭环入文，
> 修订记录见 §11。唯一承重柱「per-user 覆盖 admin 装零 UAC」文档证据支持、官方无正面条文，
> **列为 P0 真机实验 V-1，立碑后方可开工 P1 段**。
>
> **v4 口径（同日，boss 反馈"流程对用户太复杂"）**：用户可见面收敛为四步
> **「升级弹窗→点立即升级→升级中→完成」**，需求文本单立
> [ai-novel-c端-一键升级-需求.md](ai-novel-c端-一键升级-需求.md)。本草案两处随动：
> ① 弹窗时机从「staged 就绪」提前到「检测到新版本即弹」（未就绪时进度页显示"正在准备"，
> 后台预下载降级为隐形加速器）；② 按钮语义「重启更新/暂不/知道了」合并为
> 「立即升级/以后再说」。**机制层（§4 全部、§5、§7）不动**——复杂度全部藏在
> 第 3 步"升级中"内部；§9 拍板点 4 的"暂不/知道了"分叉语义作废，简化为"以后再说
> ＝本版本不再弹＋下载继续但不生效、至多保留一个包"。

---

## 0. 结论先行

**四步式点击升级**（Chrome/VS Code 同款形态）：

1. **后台下载**：更新检测（现有每小时一次）发现新版本后，后台静默下载 + sha256 +
   Ed25519 双验签，全程无感、不打扰写作；
2. **后台就位**：Windows 备好**已验签的静默安装器**；macOS 解包出完整新 `.app` 暂存
   （慢活在后台干完）；
3. **就绪通知**：装好那一刻通知一次（非阻塞 toast「新版本 vX 已就绪」）＋提示条常驻
   「重启完成更新」；
4. **点「重启更新」**：前端确认无在途生成→后端校验闸后落一次性标记→壳层静默安装
   （Windows 跑真安装器 `/VERYSILENT /CURRENTUSER`，macOS 瞬时换名 bundle）→
   **自动拉起新版**，完成更新。

不点就永不生效：不自动重启、不趁退出偷装（relaunch 标记带 TTL＋一次性消费，见 §4.3）；
下次会话提示条继续挂着，点「暂不」则本版本删包退回手动链。数据面零接触：安装器不装
`data\`、卸载器不清 `data\`（现有不变式），新版首启的**数据带回/迁移告知卡照旧**。

Windows 上点击后的静默安装约 10–60s（lzma2/ultra 解压），期间无窗口，装完自动回——
这是用户**主动点了重启**之后发生的等待，可接受；macOS 点击后 1–2 秒即回。

---

## 1. 现状盘点（程序面升级链路）

| 环节 | 现状 | 代码位置 |
|---|---|---|
| 检测 | 后端每小时至多一次外呼 latest.json（主域+兜底，https+可信域+公网 DNS 出站校验），状态落 `data/update-check.json`（last_check_at / cached / dismissed_version） | `client/backend/update_check.py` |
| 呈现 | 前端提示条挂顶栏之下：发现新版本＋去下载＋查看更新内容＋知道了（按版本关闭） | `client/frontend/src/components/UpdateNotice.tsx` |
| 安装 | **全手动**：用户去官网下载 Setup exe / dmg，自己跑安装器 | 落地页 + CDN `download/v{VER}/` |
| 发包 | CI 双平台构建 → 国内 CDN（exe/dmg/notes.html/latest.json，**只留近 2 版**）；仓库私有、**GitHub Release 资产用户不可达** | `.github/workflows/client-package.yml` |
| latest.json | 仅 `{version, notes?}`——落地页弹窗与 C端 检测共用的唯一版本事实源（两路消费方都只读这两键，加键零影响） | 同上 |
| 版本口径 | `novel-v{X}.db` 库文件名与更新检测共用 `schema_version` 单源，`is_newer` 永不抛 | `client/backend/schema_version.py` |
| 数据面 | 每版首启新建自己的库＋无损带回；**API Key 密文存库内**（Fernet，钥在源库 app_meta 行），搬运时转接重加密 | `migration/engine.py` `_reencrypt_dead_ciphertexts` |
| 壳层 | 单进程 pywebview + uvicorn 线程；退出链＝GUI 循环退出 → `stop_server_gracefully` → **无条件 `os._exit`**（跳过 atexit/GC，库连接不会被正常关闭）；**无单实例锁** | `client/packaging/build/pywebview_app.py` |
| Windows 安装器 | Inno，`PrivilegesRequired=admin`（UAC）、恒显位置页、`UsePreviousAppDir`；安装器**不装 data\**、卸载**不清 data\** | `client/packaging/build/installer.iss` |
| macOS | PyInstaller `.app`，**CI 用自签证书 codesign**（build_mac.sh 的 `--sign -` 只是本地通道），dmg；数据在 Application Support | `client/packaging/build/build_mac.sh`＋workflow |
| 验签基建 | 提示词包已有 Ed25519 **顶层 manifest 签名**（去 signature 键后 canonical json；trust 钥集合＋kid 轮换），公钥经 release.json 烘焙**三点同批**（config 白名单＋壳层注 env 行＋断言） | `client/backend/prompt_pack/sync.py` |

关键事实：自下载文件**不带 MOTW**（浏览器才加），静默拉起安装器不触发 SmartScreen；
`update-check.json` 今天的写者只有事件循环内一处（asyncio 天然串行），**这份隐性安全是全
设计并发面要新还的债**（§4.2）。

---

## 2. 目标与非目标

**目标**：程序面升级**一次点击**；就绪必须通知（知情但不打扰）；数据零风险；失败一律
退回现有手动链、绝不更坏；发布侧 `auto_enabled` 总闸可秒停（闸的操作路径＝独立重签
workflow_dispatch 作业，P0 交付，见 §4.1-5）。

**非目标**
- 不做「无点击自动生效」（不自动重启、不趁退出偷装——已拍板；relaunch 标记 TTL 防后门）。
- 不做数据迁移免同意（带回卡保留，`c-lossless-upgrade-design` 口径不变）。
- 不做差分/增量包；不做强更（只留闸位）。
- 便携版（`install_portable.bat`）不自动升级。

---

## 3. 总体时序

```
后台（用户在写作，全程无感）
  update-check 每小时检测 ──is_newer 且有 B──▶ 触发闸（三闸取与，见 §4.2）
    │ 下载 DATA_ROOT/updates/*.part（同步 httpx 客户端，线程内）
    │ sha256 ✕→隔离重试 ≤5；Ed25519 顶层 manifest 验签 ✕→本版本硬停自动
    ├─ Windows：staged＝已验签安装器（updates/AwesomeNovel_Setup_vB.exe）
    └─ macOS：staged＝ditto 解包的完整 .app（updates/staging/）
    ──▶ 通知一次（toast）＋提示条常驻「重启完成更新」

点击「重启更新」（用户唯一动作）
  前端（staged 按钮处理器内）：确认无在途生成/已排空保存 →
  await POST /update-check/apply ──后端：即时重取 latest.json 验签查闸＋复验文件
    ＋写目录可探针 → 落一次性 pending.json{version,file,sha256,relaunch,issued_at}
  ──成功才──▶ NativeBridge.quit_app() 销毁窗口（此路径不触发 beforeunload，
  保护必须做在按钮处理器里，不靠关窗链）
    → GUI 循环退出 → stop_server_gracefully → Popen 安装器/换名脚本（argv 直传）
    → os._exit（OS 强释文件锁；宽限期不需要 cmd 中转，见 §4.3）

装好自动回新版；首启数据带回告知卡照旧；版本对拍→记 applied＋清暂存

用户不点：不生效；下次会话提示条仍在；「暂不」＝删暂存＋本版本不再自动
```

**为什么 Windows 点击后要等 10–60s**：运行中的 exe 被文件锁，真后台装须版本化目录大改
（v1 不做）；macOS 后台解包已把点击等待压到 1–2s。日后嫌长再评快速道（robocopy 误删
`data\` 风险须另评审）。

---

## 4. 分层改动

### 4.1 发包侧（CI / client-package.yml）

1. **latest.json v2**（顶层 `version`/`notes` 不动，两路消费方零影响）：

```json
{
  "version": "0.34",
  "notes": "…首行…",
  "auto_enabled": true,
  "platforms": {
    "win": { "url": "…/download/v0.34/AwesomeNovel_Setup_v0.34.exe",
              "size": 73400320, "sha256": "…" },
    "mac": { "url": "…/download/v0.34/AwesomeNovel_mac_v0.34.zip", … }
  },
  "signer_key_id": "update-k1",
  "signature": "base64(ed25519)"
}
```

   `signature` 为**顶层键**，载荷＝整份 latest.json 去掉顶层 `signature` 后
   `json.dumps(sort_keys=True, separators=(",",":"))`——**与 prompt_pack/sync.py 现行
   规则逐字同源**（该实现只 strip 顶层 signature；验签域写错一处＝永远验不过，两端必须
   同一函数抽公共件）。
2. **签名钥**：独立 update-k1，私钥进 GitHub Secrets；公钥经 release.json 新键
   `update_pubkeys` 烘焙——**三点同批**：config `RELEASE_OVERRIDE_KEYS` 白名单＋壳层
   `_env_with_release` 注入行＋断言（漏登记＝静默无钥，评审 P0 判例在案；壳禁 import config、
   注 env 先于 config 导入的 c-shell-release-env-order 判例一并适用）。
3. **macOS 增发 zip**：`ditto -c -k --sequesterRsrc --keepParent`（zipfile 丢符号链接炸
   Frameworks）；CI 增 upload-artifact、`tcb hosting deploy`、check() 三处行。
4. **发布顺序维持「包 → manifest」**（不得反转）：sha256/size 在构建产物本地算（artifact
   往返保证字节一致）→ 部署 exe/dmg/zip → 生成部署 latest.json → 末尾校验补 zip 直链与
   signature/sha256 键断言。现行安全论证（发布失败时旧版目录是唯一下载源）押在 manifest
   最后落地；反序会造成新 version 直链 404 窗口烧重试。**旧 latest.json 指旧包＝无感，
   新 latest.json 出现即包已齐**。
5. **重签作业**：workflow_dispatch 小任务——改 `auto_enabled`/撤平台键→重签重发 latest.json
   （不重建包）。这是 §2「秒停」的操作性落点。
6. **先 v2 manifest 后新客户端**：旧客户端只读 version/notes，兼容窗口免费。

### 4.2 后端下载器（update_check.py 扩展或同目录 updater.py）

- **目录**：`DATA_ROOT/updates/`（后端零新路径逻辑；Windows 落在 `data\` 内、安装器覆写
  范围不碰 `data\` 有 §4.4 不变式背书，避开 {app} 的原意等价达成；壳层经 env
  `CLIENT_UPDATES_DIR` 读同一路径——**单一属主下发，禁止两处各自拼路径**）。
- **状态机**（落 update-check.json 新键 `auto`）：`idle → downloading → staged → applied`；
  字段 `{state, version, epoch, file, sha256, size, attempts, last_error, updated_at}`。
- **触发三闸**：`is_newer × auto_enabled × 本地开关 × 未 skip`。**与 `has_update` 解耦**
  （`dismissed_version` 会把 has_update 置 false——「知道了」只想关条，不得误停下载链；
  has_update 仅供 UI）。dev 与 `--smoke` 全链 no-op（smoke 也服务 /api，非 dev 版本会真烧
  70MB）。
- **单飞＋取消**：下载触发加锁（对照 prompt_pack `trigger_sync` 的 `_syncing` 锁＋排队
  覆盖先例），每次触发带 `(version, epoch)` 代际号与 `threading.Event` 取消位——新版本
  检出／闸翻 false／用户暂不 → 旧线程中止并清 `.part`。**禁止双线程写同一 .part**。
- **失败重试矩阵**：传输类错误（超时/断连）线程内退避重试 ≤5；环境类失败（磁盘不足/
  验签不符/闸关）线程终止、等下一次检测窗——两套模型各辖哪类写进实现，不许混。
- **下载实现**：后台线程用**同步** httpx（复用 prompt_pack/sync.py 的同步出站校验＋
  `build_sync_client` 同款）；`update_check` 里那个 async 版 `_validate_outbound_url`
  是为防 DNS 冻事件循环设计的，**线程里不要复用错版本**。断点续传取决于 CDN 的 Range
  支持（存疑项，决定重试是续传还是整包重下）。
- **写者纪律**（P1 级要求）：`update-check.json` 改 **tmp＋os.replace 原子写**；`auto` 块
  单写者＝下载协调线程（其余端点只投递指令不落盘）；pending.json 唯一属主＝后端进程写、
  壳层只读，自愈计数落独立标记文件。§10 增「并发写撕裂」用例。
- **端点**：`/api/update-check` 响应增 `auto` 块；`POST auto-skip`（删暂存＋本版本不再自动）；
  `POST apply`（见 §4.3——校验闸＋写一次性 pending，成功才返回 ok）。

### 4.3 壳层（pywebview_app.py）

- **apply 链**（`POST /apply` 后端侧完成）：即时重取 latest.json 验签→闸为 true？→对 staged
  文件复验 sha256→**用现成 `_install_dir_writable` 探针预检当前用户 token 可写 {app}**→
  写 `pending.json{version,file,sha256,relaunch:true,issued_at}`。任一步不过：返回失败、
  **不落标记不毁窗**，提示条升手动。（闸生效延迟若不做即时重取，验收措辞就得收缩——
  本设计选做重取，成本是一次带外呼的用户手势。）
- **relaunch 一次性＋TTL**：壳层退出链读 pending 时 `issued_at` 超 10 分钟或已消费 →
  不安装。防「点了 apply 拖着不关、三天后随手关窗被偷装」回潮。
- **桥顺序**：staged 按钮处理器＝前端先排空保存/确认在途 → `await /apply` 成功 → 才调
  `NativeBridge.quit_app()`（新增桥方法，仅 `window.destroy()`）。**destroy 不触发
  beforeunload**，关窗保护在前端 JS 里、桥路径绕不过去就得靠按钮自己实现同口径。
- **Windows apply**：`subprocess.Popen([installer, "/VERYSILENT","/SUPPRESSMSGBOXES",
  "/NORESTART","/CURRENTUSER","/MERGETASKS=!desktopicon","/DIR="+str(Path(sys.executable).parent),
  "/LOG="+…,"/AUTOLAUNCH=1"], creationflags=DETACHED_PROCESS)`——**argv 直传，禁止
  `cmd /c … ^&` 字符串拼接**（caret 语义会把它吃成 timeout 的字面参数，安装器根本不被
  拉起，评审 P1）。无需自造 2s 宽限：本进程随后 `os._exit`，OS 强释句柄；第三方杀软
  瞬态句柄由 Inno 默认 `CloseApplications=yes`（静默下会关闭并继续）＋失败重跑兜。
  **`/DIR` 优先性预检**：注册表卸载键 AppDirectory 与 /DIR 值不等 → fallback manual
  （两者对已注册安装同值是常态；分歧只在残注册/移盘异常态，真机 V-7 钉死）。
- **Windows 自愈**：启动时检测「pending 存在＋本机版本≠pending.version」→ **不在本次
  启动时重跑安装器**（此刻本进程自己的 exe 被锁，覆写必败）——保留标记，下次走退出链
  apply 自然生效；标记计数上限一次（独立标记文件，防环），再败升手动。
- **macOS apply**：bundle 路径＝`Path(sys.executable).parents[2]`（**禁用
  `get_install_dir()`——mac 冻结态它返回数据目录，拿它当 bundle 会把用户数据目录搬走**）。
  换名前 `os.path.exists(dev)` 同卷预检（暂存盘≠目标盘时 rename 塌 EXDEV：外置盘 home
  是真实形态——跨卷走 copy-swap 慢路径或降级手动）。两记改名＋拉起放进**一次性 detached
  `/bin/sh -c 'mv bundle bundle.old && mv staging/App bundle && open bundle'` 子进程**，
  崩溃窗收窄为两 syscall 之间；解包 staged 时 `codesign -v` 冒验。「主路径缺失＋
  `.AwesomeNovel-old.app` 在场」的死态无进程可自愈（没有东西会启动），§7 给手册恢复命令
  （old.app 以点开头 Finder 不可见，命令须含通配）。old.app 清理仍按「新版首启装载成功」
  之后。
- **日志**：全程 `auto-update:` 前缀写 startup.log，判据见 §7。

### 4.4 Windows 安装器（installer.iss）

1. **加一行** `PrivilegesRequiredOverridesAllowed=commandline`＋**choco 钉版**（Inno 行为
   强依赖版本：静默默认应答表/提权守卫 7.x 已变过；升级 Inno＝打包链改动，走 dispatch
   演练）。⚠️「admin 装过的机器 /CURRENTUSER 静默覆盖零 UAC」＝全设计承重柱：官方条文
   支持参数覆盖、commandline 模式下 UsePreviousPrivileges 实效忽略、Default.isl 无冲突
   提示消息——**间接证据齐但无正面成文组合**，P0 真机 V-1 立碑后方可开工 P1。
2. **`/AUTOLAUNCH=1`（带值）**；`[Code]` 判 `ExpandConstant('{param:AUTOLAUNCH|}')='1'`。
   裸 flag 形态按官方 `{param:}` 语义落「value could not be determined」取默认值分支——
   **可能永不触发**（评审 P1）；三种形态真机 V-3 验过再定。
3. **[Run] 自拉起条目**：`Filename: {app}\{#MyAppExeName}`＋`Check:` 判 param＋
   `Flags: postinstall nowait`。**不带 `skipifsilent`**（静默下恒跳过＝自动拉起死键），
   **不带 `runhidden`**（SW_HIDE 起 GUI 是否显示未证）；`postinstall` 默认以原始用户令牌
   启动——恰满足「壳层 GUI 普通身份」铁律，勿加 `runascurrentuser`。手动安装不带参数→
   Check 不过→不多出勾选框。
4. **per-user 覆盖 admin 装的后遗症全清单**（比 v2 认知更大，求诊手册逐条收录）：
   - 卸载双条目：新旧 UninstallString 同指被覆写的 unins000.exe（两条款暂时都能卸）；
     但任一侧卸载后**另一根键成悬挂幻影条目**（点开报找不到文件）——手册给一条
     **管理员** `reg delete` 出口；low 权限清不了 HKLM。
   - 开始菜单双快捷：旧 All Users 快捷＋per-user 新建（同路径，功能正常外观双份）。
   - `{commondesktop}` 图标：per-user 静默可否写 Public Desktop **无条文、环境相关**，
     失败即中止整链翻车——更新器已按 §4.3 传 `/MERGETASKS=!desktopicon`（官方支持），
     旧图标本就在，无损；真机 V-2 复验。
   - `[Dirs]` ACL：per-user 无权改 ACL 时**静默跳过不中止**（官方条文）——正常落点
     （用户 own 目录）本就可写，无需处理。
   - 数据不变式：`data\` 不在覆写/删除清单——静默与手动同保证。

### 4.5 macOS 发包与换包

- CI 增 zip 产物（4.1-3）；换包细节全在 §4.3 mac 段（bundle 路径来源、同卷预检、一次性
  换名子进程、codesign 冒验、死态手册命令）。
- Gatekeeper 无忧：自下载无隔离属性；现 CI 实为**自签证书**签名（非 ad-hoc，v2 文中
  表述已纠），换路径不换签名身份，登录项/TCC 本期无敏感面（无 launch-at-login 代码）。

### 4.6 前端（UpdateNotice 三态 + 通知）

- 提示条三态：downloading 前现状文案（手动链保底）；**staged＝「新版本 vX 已就绪」＋
  「重启更新」（主按钮，走 §4.3 apply→quit 顺序）＋「暂不」**；失败/降级回手动文案。
- **就绪通知**：staged 完成 toast 一次（按版本记忆）＋提示条常驻。staged 后用户点
  「知道了」＝只关条（dismissed 语义），下载/就位链**不受影响**（触发解耦，§4.2）；
  「暂不」才退包。
- **时效缝**：`auto.state` 处于 downloading 时轮询提速 1 分钟（轮本地端点，真实外呼仍
  小时节流），staged/回落恢复 15 分钟——就绪延迟 ≤1 分钟。
- **重启保护在按钮内**：确认无在途生成＋排空保存后才 `await /apply`（§4.3，不依赖
  beforeunload）。
- 设置开关「自动更新」默认开（`auto_enabled_local`，与服务端闸取与）。

### 4.7 版本共存·切换·回滚（程序层单槽 × 数据层多代）

- **程序层＝单槽原地**：Windows Inno 覆写 `{app}`（旧二进制覆写即消亡，路径不变）；
  macOS 两记改名（`.old.app` 暂留＋暂存顶上）。磁盘上任何时刻只有一个可运行当前版，
  无版本选择逻辑。
- **数据层＝多代共存（现行不变式）**：`data\` 全部库只增不删——回滚的真正保险。

| 阶段 | 状态（修正版） | 回滚/恢复路径 |
|---|---|---|
| staged 未点 | 什么都没发生 | 「暂不」＝删暂存；不点＝永不生效 |
| 点击后安装中途失败/断电 | **程序目录新旧混合态（Inno 无自动回滚承诺，v2 表述已纠正）**；`data\` 不在覆写清单故数据无恙 | 自愈＝下次退出链**重跑覆盖安装**（覆盖安装幂等是 Inno 强项）；exit 4/5＝疑似文件占用/取消→看 installer.log 尾；7/8＝prepare 拒绝；非零皆升手动观察 |
| 装成但新版启动失败 | Windows：旧二进制已被覆写，无自动出口 → 重装旧版，**源＝CDN 仅存近 2 版目录**（仓库私有、GitHub Release 资产用户不可达——v2 该承诺已撤；更早版本走客服/手动链）；macOS：`.old.app` 改名回原位（手册一条通配命令） | mac 首启成功前不清 old.app＝廉价退路；主路径缺失死态按 §4.3 手册恢复 |
| 新版已正常使用 | 手动降版重装；新版期间写入的书在新版库，**降级后不可见**，重新升级才回来 | 数据零丢失；备份恢复同现行口径 |

明确取舍：Windows 不做版本化目录双共存＋launcher 切换（便携铁律「安装目录＝数据目录」
不可拆，打包链大改）——v2 评估项；v1 不做「一键回滚」（本机不留历史安装包）。

### 4.8 状态交接三层模型（A 关闭 → B 启动，「100% 一致」的定义）

| 层 | 内容 | 通道 | 一致性保证 |
|---|---|---|---|
| ① 内存态 | 未落盘稿、在途生成 | staged 按钮处理器内：排空保存＋在途确认（§4.6，桥路径不经 beforeunload） | 先排空再退出——内存态被机制归零，不是承诺 |
| ② 程序无关持久态 | config.json、提示词包安装状态、update-check.json、备份、shell.json | 安装覆写范围不含——程序换了状态原封不动，B 直读 | 覆写白名单物理隔离；提示词包 localkey（DPAPI/Keychain 绑机器+用户）B 照解 |
| ③ 版本限定态 | 本书 `novel-vA.db`＋**库内 API Key 密文**（Fernet，钥在源库 app_meta 行——不在层②，v2 张冠李戴已纠正） | B 首启新建 `novel-vB.db` → 候选扫描发现 A 库 → 告知卡同意 → 逐表映射**抄本**（A 库只读）→ **Key 随搬运＋转接重加密同批到达**（`_reencrypt_dead_ciphertexts` 判例） | 无损升级链既有验收：CI 历史世代全量重放＋源库零接触＋rows_missing 逐表核对＋结果卡实名明细＋值域宁低勿高。**拒绝告知卡＝书与 Key 都不达（同命运）** |

**「100%」诚实拆解**：②③＝机器保证（已落盘的一个不丢）；①＝机制归零。
**WAL 现实（v2 错误前提已纠正）**：退出链尾部是 `os._exit`，无末连接关闭、无 dispose——
**正常退出后 `-wal`（乃至 `-shm`）残留是常态**。安全性靠数据件口径而非 checkpoint 假设：
搬运指纹＝主件+wal（`candidate_stamp` 单源，**-shm 永不入指纹**，c-carry-modal-reshow
判例），搬运＝拷主件+wal→副本上 checkpoint（`db_lifecycle` 现行实现）。实现者不得据
「已 checkpoint」省掉 wal 分量。A 库永远留存且 B 永不回写——降回 A 版仍见 A 期全部书。

---

## 5. 安全模型

| 面 | 措施 |
|---|---|
| 传输 | 仅 https＋可信域（烘焙两台静态托管）＋解析结果全公网；下载线程用同步出站校验版（§4.2） |
| 完整性 | sha256 双验（下载后＋apply 前）；`platforms.url+sha256` 同受顶层签名覆盖 |
| 来源 | Ed25519 顶层 manifest 签名（独立 update-k1，kid 轮换）；验签不符＝本版本硬停＋高亮日志 |
| 降级 | `is_newer` 单源只升不降；旧签名 manifest 重放被序挡住；`auto_enabled` 秒停（重签作业 P0 交付）＋**apply 时即时重取查闸**（闸关拒落标记，v2 缺口已补） |
| 执行 | 只拉起自下载验签过的安装器；/DIR 钉当前目录＋注册表 AppDirectory 一致预检；写探针预检不过**不落标记不毁窗** |
| 清单 | staged 只留最新；`.part`/隔离区定期清；pending 一次性＋TTL |

---

## 6. 与既有设计的关系

- **c-lossless-upgrade-design**：程序面点击升级与数据面知情链互不替代；升级后首启带回卡
  照旧，两弹窗共用宿主排队（数据>能力）口径不变。
- **c-update-strip-below-appbar**：挂位复用，文案三态化。
- **client-update-notify capability**：立项走 openspec propose，同批扩 Requirement。
- **单实例锁**：**P0 硬依赖**（v2「建议同批」升格）——双开时两实例各有提示条、抢写
  同一运行时文件，叠加双下载/双装后危害放大；且「第二个静默安装器与 setup mutex 的
  真实交互」官方未成文（存疑 V-6），在锁落地前无法出真绿验收。

---

## 7. 失败面与日志判据（startup.log `auto-update:` 前缀）

| 现场 | 日志判据 | 行为 |
|---|---|---|
| latest.json 拉取失败 | 现行静默 | 与今天一致 |
| manifest v1（旧格式窗口期） | `manifest v1, auto disabled` | 手动提示条照旧 |
| sha256 不符 | `sha mismatch, quarantined (n/5)` | 隔离退避重试 |
| Ed25519 验签不符 | `SIGNATURE REJECT ver=X kid=Y` | 本版本硬停自动 |
| 下载中断/磁盘不足/闸关/被取消 | `download aborted (reason)` | 按 §4.2 重试矩阵分流 |
| **apply 被拒**：闸已关／复验失败／写目录不可写 | `apply refused (gate/verify/dir)` | **不落标记不毁窗**，升手动 |
| relaunch TTL 过期 | `relaunch expired, skipped` | 不安装，标记作废 |
| 安装器退出码≠0 | `installer exit=N`（N 语义见 §4.7 行 2） | 混合态＋下次退出链重跑一次；再败升手动 |
| /AUTOLAUNCH 未触发 | `autolaunch missing` | 用户手动打开即新版 |
| 重启后版本≠pending（Win） | `pending kept (heal at next exit)` | 下次退出链 apply，上限一次 |
| macOS 主路径缺失＋old.app 在场 | 壳层无进程可跑（死态） | 手册：`mv ~/.…AwesomeNovel-old.app 原名`（通配显示） |
| macOS 跨卷/父目录只读 | `cross-volume/readonly, fallback manual` | 回手动链 |

---

## 8. 分期落地

- **P0 打包侧地基＋承重柱**（先行可发，旧客户端零影响）：
  ① latest.json v2 发布链＋签 manifest＋mac zip＋重签作业；② installer.iss
  Override＋`/AUTOLAUNCH=1` [Run] 项＋choco 钉版；③ **V-1 真机：admin 旧版→
  /CURRENTUSER 静默覆盖零 UAC＋V-2/V-3 组**（承重柱立碑）；④ 单实例锁立项。
  ⚠️ dispatch 演练只验构建，运行期 UAC/参数语义必须真机（判例：打包链改动先演练）。
- **P1 Windows 闭环**：下载状态机（单飞/取消/原子写）＋验签三闸；apply/TTL/预检；
  桥 quit_app＋提示条三态。
- **P2 macOS 闭环**：解包 staged＋同卷预检＋一次性换名链＋死态手册命令。
- **P3 信任面**：设置开关、求诊手册（双卸载条目幻影态/reg delete 出口/双快捷）。

---

## 9. 拍板点

**已拍板（2026-10-13）**：主流程＝后台下载→就位→就绪通知→点「重启更新」→静默生效＋
自动拉起；不自动重启、不趁退出偷装；staged 主按钮「重启更新」。

**待拍板（推荐意见）**：
1. 签名钥独立 update-k1（推荐）vs 共用。
2. 安装器单产物 Override 双模（推荐）vs 双安装包——§4.4-4 后遗症清单是代价面。
3. 「自动更新」默认开＋设置可关。
4. 「暂不」＝删包＋本版本不再自动；「知道了」仅关条不触包（§4.2 解耦后语义才自洽）。

---

## 10. 验收方案

- **pytest**：验签（好/坏/缺 platforms/钥轮换/顶层域）、状态机与重试矩阵分流、三闸×
  dismissed 解耦、**并发写撕裂**（端点×下载线程交错）、单飞与代际取消、TTL 一次性、
  apply 拒绝臂（闸/复验/探针）、smoke/dev no-op。
- **壳层**：argv 拼装（中文＋空格＋`&` 用户名路径抵达）、/DIR≠注册表值拒绝、mac bundle
  路径来源钉测、跨卷预检、`--smoke`/普通关窗零行为变化。
- **真机 V 组（P0 出碑）**：仿真实验包已就绪（`docs/design-c/drafts/upgrade-lab/`，
  Setup_Lab 1.0.0/1.0.1 双包＋README 手册 E1–E9＋判读表，2026-10-13 mac docker 编译通过），
  发给测试同学照手册跑即可；判过标准＝B/C/D/E/G 五项全绿。仿真不覆盖"运行中被覆盖"场景
  （拉起件是记事本非常驻进程），须 E9 真实包复跑补验。
  - V-1 admin 装旧版→/CURRENTUSER 静默覆盖：零 UAC 零闪现、退出码 0、data\ 逐字节不动、
    新版自动回；对照组不带 /CURRENTUSER 必弹 UAC。
  - V-2 {commondesktop} per-user 可写性（挂了就靠 !desktopicon，复测到绿）。
  - V-3 AUTOLAUNCH 三形态（裸/=1/缺省）＋[Run] 项窗口可见性。
  - V-4 argv 直传中文空格&路径抵达（installer.log 落点为证）。
  - V-5 文件被占形态→exit 4/5→下次退出链重跑成功。
  - V-6 双开两实例先后点重启（单实例锁未落前仅观察记录）。
  - V-7 /DIR vs UsePreviousAppDir 分歧态优先级。
  - V-8 断电/强杀混合态＋自愈判据演练；mac 两 mv 之间 kill -9→手册恢复。
  - V-9 httpx 下载件无 Zone.Identifier→零 SmartScreen。
  - V-10 Inno 钉版后 isl 编译告警清单存档。
- **端到端真机清单**（P1 段）：staged→点重启→新版带回卡照旧→拒绝迁移时书与 Key 均不达
  （层③同命运）→暂不/延迟关窗不偷装→闸 false 重发后 apply 被拒→mac 拖装位瞬时换名。

---

## 11. 评审修订记录（2026-10-13，双路架构评审）

评审结论：**有条件可立项**——运行时侧 P1×4、打包侧 P1×4 已全部闭环入文；承重柱（零 UAC）
证据倾向成立但必须 V-1 真机立碑。主要修订：

| # | 原稿问题（评审发现） | 处置 |
|---|---|---|
| 1 | API Key 归为层②/DPAPI——实为库内 Fernet 密文，随搬运重加密（层③） | §4.8 改写＋拒绝迁移同命运条款 |
| 2 | 「优雅退出末连接 checkpoint WAL」代码里不存在（os._exit） | §4.8 改「残留是常态，主件+wal 口径」 |
| 3 | update-check.json 多写者撕裂＋pending 跨进程双写 | §4.2 单写者＋原子写＋唯一属主 |
| 4 | 下载无单飞/取消、双重试模型打架 | §4.2 锁＋epoch 代际＋失败矩阵 |
| 5 | relaunch 标记不过期＝偷装后门 | §4.3 TTL＋一次性 |
| 6 | updates 目录双路径口径漂移风险 | §4.2 统一 DATA_ROOT/updates＋env 下发 |
| 7 | 线程复用 async 出站校验＝用错版本 | §4.2 同步版＋build_sync_client |
| 8 | 桥 destroy 绕不过 beforeunload、顺序未闭合 | §4.3/§4.6 apply 成功才 destroy、保护在按钮内 |
| 9 | `cmd /c … ^&` 安装器根本不被拉起 | §4.3 argv 直传 Popen |
| 10 | 裸 /AUTOLAUNCH 参数语义、skipifsilent/runhidden 死键陷阱 | §4.4 `=1`＋Check＋正确 flags |
| 11 | 「Inno undo 回滚旧版完好」夸大 | §4.7 改混合态＋幂等重跑 |
| 12 | 回滚源「GitHub Releases 全历史」不存在（仓库私有） | §4.7 撤承诺，源＝CDN 近 2 版 |
| 13 | 「先 manifest 后发包」制造 404 窗、顺序反了 | §4.1-4 维持包→manifest |
| 14 | auto_enabled 对已 staged 包无 apply 检查点 | §4.3 apply 即时重取查闸 |
| 15 | 后遗症清单不全（幻影卸载条目/双快捷/commondesktop 链断候选/ACL 静默跳过） | §4.4-4 逐条＋!desktopicon＋手册 |
| 16 | mac bundle 路径没指明（get_install_dir 会搬走数据目录）＋跨卷 EXDEV | §4.3 parents[2]＋同卷预检 |
| 17 | Windows 启动时自愈＝锁自己 | §4.3 改下次退出链 |
| 18 | 「知道了」误停下载链（has_update 闸） | §4.2 触发与 dismissed 解耦 |
| 19 | mac CI 实为自签证书非 ad-hoc | §1/§4.5 纠正 |
| 20 | Inno 不钉版＝静默链语义随版本漂移 | §4.4/§8 P0 choco 钉版 |
| 21 | 单实例锁「建议」强度不足 | §6 升 P0 硬依赖 |

```
（本草案仍未立项；下一步＝§9 拍板＋P0 四件套开工令。openspec 提案届时走 propose 流程。）
```
