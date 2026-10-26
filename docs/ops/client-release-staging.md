# C端 发版灰度通道 runbook（c-update-staging-channel）

> 心智模型：同一生产托管、**一份安装包实物、两个指路牌**。
> `download/v<VER>/` 实物目录两渠道共用；`download/staging/latest.json` 灰度指针
> （发版自动写）；`download/latest.json` 生产指针（只在晋升时推进，全体用户读）。

## 渠道布局

| 路径 | 是什么 | 谁写 | 谁读 |
| --- | --- | --- | --- |
| `download/v<VER>/…exe/…dmg/notes.html` | 版本化实物（只增不改） | tag 流水线 | 两个清单的下载直链 |
| `download/staging/latest.json` | 灰度指针 | tag 流水线 | 只有指向它的本机 |
| `download/latest.json` | 生产指针 | 仅晋升作业（及 resign 总闸） | 落地页弹窗＋全体用户 |

## 发版三步

### ① 发版（push tag，与过去完全一样）

`git tag -a v0.41 -m "更新说明首行" && git push origin v0.41` → 流水线自动：
GitHub Release ＋ 双包/notes.html 落 `download/v0.41/` ＋ **灰度 latest.json 指到 0.41**。
生产 `latest.json` 一个字不动，用户零感知。流水线日志末尾打印灰度验收入口 URL。

### ② 本地验收（提前跑完整更新链）

**v0.41+ 的客户端（推荐，文件开关）：**

在数据目录建 `update-channel.yaml`（内容照抄即可，自带注释）：

```yaml
# 灰度渠道开关：删掉本文件或改成 prod 即回生产渠道
# staging = 从灰度目录检测更新 ｜ 也可直接写任意清单地址：
# update_url: https://example.com/some/latest.json
channel: staging
```

- Windows：`{安装目录}\data\update-channel.yaml`
- macOS：`~/Library/Application Support/AwesomeNovel/data/update-channel.yaml`

然后启动应用 → 账号菜单点**「检查更新」**（绕过 1 小时节流，立即真实外呼灰度）
→ 应提示「发现新版本 v0.41〔灰度渠道〕」→ 走「重启更新」完成升级。

**0.40 过渡（0.40 还没有文件开关，用环境变量，env 优先于烘焙）：**

- Windows：建 `启动灰度.bat`：
  ```bat
  @echo off
  set CLIENT_UPDATE_URL=https://www.awesomenovel.com/download/staging/latest.json
  set CLIENT_UPDATE_URL_FALLBACK=https://ai-novel-test-d1ghsr86ra814c12c-1468883265.tcloudbaseapp.com/download/staging/latest.json
  start "" "C:\Program Files\AwesomeNovel\AwesomeNovel.exe"
  ```
- macOS（`open -a` 不传环境变量，须直启二进制）：
  ```bash
  CLIENT_UPDATE_URL=https://www.awesomenovel.com/download/staging/latest.json \
  CLIENT_UPDATE_URL_FALLBACK=https://ai-novel-test-d1ghsr86ra814c12c-1468883265.tcloudbaseapp.com/download/staging/latest.json \
    /Applications/AwesomeNovel.app/Contents/MacOS/AwesomeNovel &
  ```

**确认开关真的生效**（防糊涂账三查）：

1. 检查更新 toast 带〔灰度渠道〕后缀——没有后缀＝没生效；
2. `data/update-check.json` 的 `cached.source_url` 应为 `…/download/staging/latest.json`；
3. 装上 v0.41+ 后 `data/update-channel.yaml` 是你亲手建的那个文件。

验收发现问题 → 修 → **新 tag 重走**（tag 不可变；如 v0.41 有问题发 v0.41.1）。

### ③ 晋升（GitHub 网页三步）

1. 仓库 → **Actions** → 左侧选 **「C端 更新灰度晋升（staging → 生产）」**；
2. **Run workflow**：`expected_version` 填验收版本号（如 `0.41`）；首次可勾 `dry_run`
   ——只做全部校验不落生产，日志打印「生产 v0.40 → v0.41」预览与灰度清单内容；
3. 去掉 dry_run 再跑一次＝真晋升。作业守护闸（任一不过即拒绝且不碰生产）：
   清单合法、双平台域名可信、`auto_enabled=true` 必带签名、**灰度版本严格新于生产
   现网**（防倒挂）。晋升为字节原样拷贝，签名随字节走、无需重签。

晋升后：落地页下载弹窗即刻指新版；已装用户最迟 1 小时内自动检测并后台下载
（用户手动「检查更新」立即生效）。

## 逃生口

- **紧急停发**（已晋升后发现坏版本）：跑现有「C端 升级清单重签（auto_enabled 总闸）」
  → `auto_enabled=false` 一拨即停全网自动升级；版本回指旧版也走该作业。
- **晋升守护拒绝**：看日志具体哪条闸（版本倒挂/域名可疑/缺签名/对拍不符），
  按提示处置；「生产已是该版本」属正常幂等拒绝。
- **灰度清单不对**：直接重跑 tag 流水线不可行（tag 已存在），发新 tag。

## 判例与注意

- staging 与生产**共用版本化实物**：灰度验收跑的包＝将来给用户的包，一字不差。
- prune 只删 `download/v<VER>/` 旧目录（保留最近 2 版），两个 latest.json 永不在删除路径。
- 落地页/S端 读的是生产指针：晋升前落地页仍显示旧版，属预期。
- `/download/download/…` 双拼会被静态托管 SPA 兜底页接住（200+HTML 冒充 JSON）——
  排查「渠道不可达」时先核对 URL 拼写（历史实锤 10-14）。
- 0.40 及更早客户端没有文件开关，过渡期一律用环境变量法。
