# 真实包 · Windows 静默升级验证手册（lab E9 实装版）

> 适用对象：分支 `silent-upgrade-lab` 打出的真实安装包（约 70MB，含全套应用）。
> 目的：在仿真包（README.md）全绿后，用**真程序**再走一遍承重柱判据；顺带首验
> 「换版后数据层完好」——书一根不少、迁移告知卡照旧。

## 准备（5 分钟）

1. **机器**：一台装着正式版「爱小说」的 Windows 10/11（就是你的日常账户，**别**用管理员
   PowerShell——正式版是正常双击装的，正是要覆盖的对象）。
2. **拿包（二选一，推荐 A）**：
   - A. 在这台 Windows 上装 GitHub CLI 后执行（命令行下载**不带**浏览器拦截标记，
     与真实升级链的下法一致）：
     ```powershell
     gh run download 38396679329 -n AwesomeNovel-Setup-win -D $env:USERPROFILE\Downloads
     ```
     得到 `AwesomeNovel_Setup_vsilent-upgrade-lab.exe`（以实际产物名为准）。
   - B. 我这边下载后传给你（U 盘/网盘/SCP 均可）。
3. **录屏**开始（弹窗可能只闪现一下，录像兜底）。
4. **先正常退出爱小说**（右下角关闭即可——真实升级链里这一步由程序自己完成，
   手动实验等效替代）。

## 第一步 · 留底（关闭应用后立刻做）

普通 PowerShell（开始菜单直接搜 PowerShell，**不要**右键"以管理员身份运行"）：

```powershell
$APP = "$env:LOCALAPPDATA\Programs\AwesomeNovel"
Get-ChildItem "$APP\data" | Format-Table Name, Length, LastWriteTime
Get-FileHash "$APP\data\novel-v0.33.db" -Algorithm SHA256   # 库文件名以实际为准
```

把哈希抄下来——**结尾要一模一样对回去**。
（若你当初自定义过安装位置，把 `$APP` 换成那个目录。）

## 第二步 · 核心实验：一条命令静默升级

把下面整段贴进**同一个**普通 PowerShell（安装包路径按实际改）：

```powershell
$PKG = "$env:USERPROFILE\Downloads\AwesomeNovel_Setup_vsilent-upgrade-lab.exe"
$APP = "$env:LOCALAPPDATA\Programs\AwesomeNovel"
& $PKG /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER /MERGETASKS=!desktopicon /DIR="$APP" /LOG="$env:TEMP\lab-real.log" /AUTOLAUNCH=1
"EXIT=$LASTEXITCODE"
```

**盯三个判定点**（约 10–60 秒静默安装期，期间桌面应该完全安静）：

| # | 判定点 | 期望 |
|---|---|---|
| B | 全程 | **零弹窗**——没有"是否允许此应用对设备进行更改"，没有安装界面，没有任务栏闪现 |
| C | 命令最后一行 | `EXIT=0` |
| E | 装完后 | 爱小说**自己开了起来**（这是安装器拉起的） |

**E 之后在应用里再看两点**：

| # | 判定点 | 期望 |
|---|---|---|
| D | 书架 | 你的书**一根不少**；首次启动出现**「数据迁移」告知卡**属预期（测试包身份是
     dev 哨兵库，照旧走无损带回；拒绝它也不损原库） |
| D2 | 关掉应用重跑第一步的两条命令 | `data\` 里原库文件**哈希一字不差**、目录里没少文件 |

## 第三步 · 对照实验（证明这台机器的实验有效）

再跑一次同样的命令，**只删掉 `/CURRENTUSER` 这一个参数**：

- 期望：**这次弹出 UAC 确认框**——出现即点"否"取消（不要装第二次）。
- 含义：对照组弹、实验组不弹，才证明"免 UAC"是那个参数的功劳，而不是机器本来就不弹。
  若对照组也不弹＝这台机 UAC 被调过，换一台机器重做。

## 收尾 · 回到正式版（随时可做、无损）

官网重新下载当前正式版（v0.33）安装包，正常双击装回原位即可——你的原库全程没被动过。

## 失败怎么办

任何一步不符期望（弹了框 / EXIT≠0 / 没自动起来 / 书少了）：**不用修，收集三样发回来即是
最大成果**（这正是真机才能兜住的官方没写明的行为）：
1. 屏幕录像；
2. `%TEMP%\lab-real.log` 全文（安装器日志）；
3. 应用日志目录 `<安装目录>\logs\` 里最新两份文件。

判读结论会决定 P1 是照案开工，还是切双安装包路线（设计草案 §4.4）。
