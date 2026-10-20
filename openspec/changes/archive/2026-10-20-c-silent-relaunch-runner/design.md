# c-silent-relaunch-runner · 设计

## Context

「重启更新」链在 c-silent-upgrade 落地时的形态：退出链直接 `Popen` 安装器后立刻
`os._exit` 放锁，正确性依赖「Inno 初始化比进程死亡慢」这一时序赌注。v0.35→0.36
生产真机翻车（点重启→弹回旧版），暴露该赌注的失败面：exe 在安装器动手时仍被占
（杀软首扫／残留实例）⇒ 安装器静默重试后中止 ⇒ `[Run]` 自动拉起不跑，而某个旧形态
窗口已把用户接回旧版。

## Decisions

1. **安装执行权收编给安装目录之外的 runner**。安装器要覆写 {app} 里的每个文件，
   执行体若住在 {app}（如用应用自身 exe）会自锁——故选系统自带、必然在 {app} 之外的
   Windows PowerShell 5.1（取 WINDIR 全路径防 PATH 劫持，缺失回落 PATH 名）。
2. **等尸→同步装**。runner 先 `Wait-Process -Id <父pid> -Timeout 60` 等本应用进程
   完全退出（有界：父 pid 复用属理论路径，超时放行，Inno 自带 4 次重试兜残余锁窗），
   再 `& installer` 同步执行（PS 对 GUI 子系统程序同样阻塞到退出）。由此安装成功
   严格先于安装器的 `[Run]` 自动拉起——任何被拉起的窗口必然是新 exe；装失败＝
   不拉起，回 pending 重试＋手动链。
3. **脚本下发零转义面**。整段脚本文本经 `-EncodedCommand`（UTF-16LE base64）下发，
   不经过任何 shell 解析器——路径空格/中文/撇号（PS 单引号内 `''` 翻倍转义）全部
   安全；长度 ~KB 级远低于 CreateProcess 32K 限。
4. **留痕进诊断面**。runner 把 `wait_ms`、`parent_alive_after_wait`（超时后父进程是否
   仍活——分辨「锁源在父进程之外」与「装在活进程身上」）、`installer_exit`、
   `install_seconds` 追加写 `data/updates/installer-runner.log`；与 Inno 自身的
   `installer.log` 并列，同为「暂不」清理的保留项。
5. **失败语义不扩散**。runner spawn 失败原样上抛（main 兜底留日志）：attempts 不递增、
   pending 留给下次退出链重试；闸门（TTL/存在性/sha/平台）与重试上限全部不动——
   本 change 只改「谁等谁死」，不改任何可观察契约。

## Risks / Trade-offs

- CI 无 Windows/PowerShell，runner 脚本只有解码形状断言、从未真执行——PS 语法级错误
  会表现为「无安装＋无 runner 日志」，由 pending 重试＋手动链兜底；真机验收第 2 条
  （日志出现 `installer_exit=0`）同时验证脚本可执行。
- AppLocker/受限语言模式等极端环境会挡 PowerShell——落点同上（可恢复）。
- PowerShell 启动开销 ~1 秒（发生在旧窗已关之后），用户无感。
