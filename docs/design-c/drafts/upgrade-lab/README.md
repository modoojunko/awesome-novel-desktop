# 升级「免 UAC 静默安装」承重柱 · 真机实验手册

**验什么**：用户点了「立即升级」后，程序能不能**一次系统确认框都不弹**，自己把自己换成
新版、再把书完好无损地交回来。这是整个自动升级方案的命根子——过不了，方案换道。

**为什么能先拿仿真包验**：被测的是**安装器行为**（权限参数、覆盖、拉起、数据不变），
跟真实应用里那 70MB 无关。仿真包 2MB、几秒装完、可反复折腾、绝不污染已装的爱小说。
全绿后再用真实包复跑一遍 E9 收尾。

**材料**（都在本目录，拷到测试 Windows 机）：
- `out/Setup_Lab_1.0.0.exe` ←「旧版 A」
- `out/Setup_Lab_1.0.1.exe` ←「新版 B」
- 本文件

**环境**：Win10/11 真机或虚拟机（快照可回滚更好）。**普通家庭用户账户**——就是日常登录
用的那个，它通常是「管理员组账户、但以普通权限运行」（这正是绝大多数用户的真实态）。
**不要**预先关掉 UAC。全程建议**开屏幕录制**（弹窗会一闪而过，肉眼+录像双保险）。

---

## 步骤（照顺序做，右侧抄进判读表）

### E1 · 装旧版 A（= 用户现在手上那版）
双击 `Setup_Lab_1.0.0.exe`，一路下一步装到默认位置。
> 这一步**该弹 UAC**（这是"手动安装"，弹是对的，见判读表 A）。装完确认目录里有
> `version.txt`(内容1.0.0) 和 `data\marker.txt`(内容含 BOOKDATA)。

### E2 · 记下 A 的"体检基线"（三条命令，贴 PowerShell）
```powershell
cd $env:LOCALAPPDATA\Programs\AwesomeNovelLab
Get-Content version.txt
Get-Content data\marker.txt
```
把 `marker.txt` 那串 `BOOKDATA...` 抄进判读表 D——升级后必须**一模一样**（=你的书没被动）。

### E3 · 核心实验：静默把 A 换成 B（**全程盯弹窗 + 录像**）
PowerShell（普通权限，别右键管理员运行）里贴这一条：
```powershell
$B="$env:USERPROFILE\Downloads\Setup_Lab_1.0.1.exe"; $D="$env:LOCALAPPDATA\Programs\AwesomeNovelLab"; & $B /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER /MERGETASKS=!desktopicon /DIR=$D /LOG=$env:TEMP\labE3.log /AUTOLAUNCH=1 ; "EXIT=$LASTEXITCODE"
```
观察 5 件事，抄进判读表：
1. **有没有弹出"允许此应用对设备进行更改？"**——期望：**全程零弹窗**（判读表 B，本实验主判据）
2. 命令行末行 `EXIT=` 后数字——期望 **0**（判读表 C）
3. 装完会不会自动蹦出一个记事本窗口——期望 **会**（判读表 E，验"升级后自动回新版"）
4. 重跑 E2 三条命令：`version.txt` 变 1.0.1？`marker.txt` 还是那串 BOOKDATA 没变？（判读表 D）
5. 看 `labE3.log` 里 `LAB param[AUTOLAUNCH]='1'`——期望 **值正是 1**（判读表 F，验参数被正确识别）

**若 B 不弹框 + EXIT=0 + 书没变 → 承重柱成立，方案可以往下做。** 若 B 弹了框 → 记下时机，
这正是要靠真机才能发现的官方没写明的坑，回来我们换双安装包路线。

### E4 · 反向对照（证明实验本身可信）
再贴一次 E3 的命令，但**删掉 `/CURRENTUSER`** 那几个字，其余不动。
> 期望：**这次该弹 UAC 了**（判读表 G）。如果去掉 /CURRENTUSER 也不弹，说明这台机 UAC
> 被设成从不提示，实验无效，换台机重来。

### E5 · 参数形态（对应评审 V-3）
用 E3 命令跑两遍变体，各记记事本弹不弹：
- 把 `/AUTOLAUNCH=1` 改成裸 `/AUTOLAUNCH` → 期望（评审预判）**不弹**记事本，log 里 `param[AUTOLAUNCH]=''`
- 完全去掉 `/AUTOLAUNCH` → 不弹记事本（正常）
> 这条用来钉死生产代码必须写 `/AUTOLAUNCH=1` 而非裸 flag（判读表 F2）。

### E6 · 桌面图标可写性（对应评审 V-2）
把 E3 命令里的 `/MERGETASKS=!desktopicon` **删掉**再跑（=尝试写公用桌面图标）。
> 记录 EXIT：若 EXIT≠0 或 log 出现 icons 失败 → 说明 per-user 静默写不了公共桌面，
> 生产更新器**必须**带 `!desktopicon` 兜底（判读表 H）。

### E7 · 文件被占用（对应评审 V-5）
先故意让旧版"卡着不放"：记事本打开 `data\marker.txt` 别关，再跑 E3。
> 记录 EXIT（可能 4/5）。关记事本再跑一次 → 期望 EXIT=0 成功。
> 用来验"杀软/占用瞬时失败→重跑即恢复"的自愈语义（判读表 I）。

### E8 · 下载不带拦截标记（对应评审 V-9）
把 `Setup_Lab_1.0.1.exe` 用 Edge/Chrome 下载一次得到带标记的副本，PowerShell：
```powershell
Get-Item "$env:USERPROFILE\Downloads\Setup_Lab_1.0.1.exe" -Stream *
```
> 期望：浏览器下载的**有** `Zone.Identifier`（=手动下载会有 SmartScreen 提示）；
> 而程序自己 httpx 下载的没有 → 印证"自动链不会触发 SmartScreen"（判读表 J）。

### E9 · 真实包复跑（全绿后收尾）
仿真全绿，才用 CI dispatch 打一个带同样 iss 改动的测试版本包，在真机重复 E1→E3，
额外确认：`data\`（这回是真书稿库）升级前后**逐字节不动**、升级后首启**数据带回告知卡
照旧出现**。判读表最后一行。

---

## 判读表（填完发回来）

| # | 检查点 | 期望 | 实测 | 过/不过 |
|---|---|---|---|---|
| A | 手动装 A（E1）弹 UAC | 弹（对照组） | | |
| B | **静默换版（E3）零弹窗** | **全程无 UAC/无闪现** | | |
| C | 静默换版退出码 | 0 | | |
| D | 书稿不变（marker/version，E3-4） | version→1.0.1、marker 逐字不变 | | |
| E | 装后自动回新版 | 记事本自动弹出 | | |
| F | /AUTOLAUNCH=1 被识别 | log 值=1 | | |
| F2 | 裸 /AUTOLAUNCH 不触发 | 记事本不弹 | | |
| G | 去掉/CURRENTUSER 该弹 | 弹 UAC（证明实验有效） | | |
| H | 桌面图标 per-user 可写 | 记录 EXIT，定 !desktopicon 必需性 | | |
| I | 占用失败→重跑恢复 | 第一次可能非0，第二次0 | | |
| J | 浏览器下载有 Zone.Identifier | 有（自动下载无） | | |

**判过标准**：B＋C＋D＋E＋G 全过＝承重柱成立，P0 可开工，P1 编码启动。任一不过＝
回来换道（双安装包 / 放弃静默），**不算白跑**——这正是真机才能兜住的官方没写明的行为。

---

## 关键：这一版验证不覆盖什么（如实告知）
仿真包**不含**「旧版程序正在运行时被静默覆盖」这一场景——因为仿真的 [Run] 拉起的是记事本、
不是常驻进程。真实应用退出链 `os._exit` 放锁 → 覆盖 是否顺，得在 E9 真实包跑时专门盯
（升级瞬间旧 AwesomeNovel 进程应已消失、任务管理器无残留）。这条已在草案 §4.3 设计里，
真机 E9 补验。
