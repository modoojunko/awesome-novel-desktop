## MODIFIED Requirements

### Requirement: 安装包国内分发

系统 SHALL 在 `v*` 标签发版时把双平台安装包转存到静态托管（CloudBase Hosting）的 `/download/v<VER>/` 目录，文件名与 GitHub Release 资产 1:1（`AwesomeNovel_Setup_v<VER>.exe` / `AwesomeNovel_mac_v<VER>.dmg`；品牌更名 2026-10-05 用户拍板直接改名，不留旧名过渡产物——线上消费方须同步切到新名，且 SHALL 与本次发版同一发布窗口内完成，顺序 MUST 为「C端 出包并使灰度清单指到本版」在前、「落地页按新名部署」在后，落地页部署窗口以生产指针推进（灰度晋升）为起点；切名后的落地页 MUST NOT 早于生产指针推进上线）。转存完成后系统 SHALL 生成（需要时签名）latest.json 并转存到**灰度路径** `download/staging/latest.json`——发版 MUST NOT 改写生产 `download/latest.json`（它只由灰度晋升作业推进，见「灰度晋升（staging → 生产）」要求）；生产 `download/latest.json` MUST 仍是落地页下载弹窗与 C端 更新检测共同的唯一线上事实源，灰度清单与生产清单 MUST 互为独立指针且指向同一份版本化实物。latest.json 载荷契约：`version` MUST 必写；`notes`（一句话更新摘要，取 tag 附注首行自动写入，无附注时可省略）与 `min_version`（强更门槛，本期仅预留字段、客户端不实现强更逻辑）为可选键，缺省 MUST 可省略。所有 latest.json 消费方（落地页下载弹窗、C端 更新检测）MUST 同时兼容"仅 version"的最小载荷与含可选键的完整载荷。转存或灰度 latest.json 写入/校验失败 MUST 使发版流水线失败，不得静默。已发布的版本目录 MUST 只增不改（版本化路径永不覆盖，使长缓存安全）。

#### Scenario: 打包产物改名时的发布顺序

- **WHEN** 某版本变更了安装包文件名（如品牌更名），且落地页按生产 `latest.json` 的版本号拼文件名
- **THEN** 发布顺序为「C端 流水线先把新名产物转存进 `download/v<VER>/` 并把灰度清单指到该版 → 灰度验收通过后由晋升作业把生产 `latest.json` 推进到该版 → 同一窗口内部署 S端 落地页」；生产指针已推进而落地页未跟上时，落地页拼出的新名直链会命中静态托管兜底页（HTTP 200 的 HTML，非安装包），故落地页 MUST 跟进部署

#### Scenario: 发版后国内直链可下载
- **WHEN** 任意 `v*` 标签发版流水线成功结束
- **THEN** `https://www.awesomenovel.com/download/v<VER>/AwesomeNovel_Setup_v<VER>.exe` 返回 200，且字节数与 GitHub Release 同名资产一致（dmg 同理）

#### Scenario: 发版只落灰度不动生产
- **WHEN** `v*` 标签发版流水线成功结束（灰度晋升尚未执行）
- **THEN** `download/staging/latest.json` 指向该新版本，生产 `download/latest.json` 保持原版本不变——普通用户客户端检测到的仍是旧版，零感知

#### Scenario: latest.json 即时生效
- **WHEN** 生产 `download/latest.json` 被推进（灰度晋升作业或总闸重签作业）
- **THEN** 落地页下载弹窗与已安装 C端 的下一次检测解析到的版本随之变化，无需任何前端重新发版

#### Scenario: 最小载荷向后兼容

- **WHEN** latest.json 仅含 `{"version": "0.13"}`（无 notes/min_version）
- **THEN** 落地页下载弹窗与 C端 更新检测均正常工作，不因缺失可选键报错

#### Scenario: 转存失败不静默
- **WHEN** 转存上传或灰度 latest.json 写入/校验未通过
- **THEN** 发版流水线以失败结束并给出明确错误，GitHub Release 可能已建但流水线状态不得为绿

## ADDED Requirements

### Requirement: 灰度晋升（staging → 生产）

系统 SHALL 提供 workflow_dispatch 形态的灰度晋升作业（`client-update-promote.yml`），把灰度清单 `download/staging/latest.json` 的**原始字节**推进为生产 `download/latest.json`：MUST NOT 重新序列化或重签——Ed25519 签名覆盖清单内容，字节一致即验签有效。晋升作业 MUST 先过守护闸，任一不过 MUST 拒绝晋升且 MUST NOT 触碰生产清单：灰度清单 JSON 合法且 `version` 形如版本串；`platforms` 含 win/mac 且各 url 域名命中可信白名单（与客户端烘焙主/兜底域同源）；`auto_enabled` 为 true 时必带顶层签名与 signer_key_id；灰度版本 MUST **严格新于**生产现网版本（生产清单缺失或不可解析视为无现网版本，允许首次/灾后晋升），防旧版倒挂覆盖新版；输入 `expected_version` 非空时 MUST 与灰度版本逐字一致。输入 `dry_run` 下作业 SHALL 完成全部校验并打印「生产 vX → vY」预览而 MUST NOT 部署。真晋升 MUST 在部署后轮询回读生产清单并比对内容一致，不一致 MUST 判红；成功输出 MUST 含「生产 vX → vY」。晋升凭证 MUST 只存在于 CI secrets（本地不持有可改生产的钥匙），每次晋升 MUST 在 Actions 留痕。紧急停发与版本回指旧版 MUST NOT 走晋升作业（走既有总闸重签作业）。

#### Scenario: 守护拒绝旧版倒挂
- **WHEN** 灰度清单版本不严格新于生产现网版本（含相同版本）
- **THEN** 晋升作业失败并说明原因，生产 `download/latest.json` 保持不变

#### Scenario: expected_version 对拍不符拒绝
- **WHEN** 输入 `expected_version` 与灰度清单 `version` 不一致
- **THEN** 晋升作业在守护闸拒绝，不部署、不触碰生产

#### Scenario: dry_run 只预演不落生产
- **WHEN** 以 `dry_run=true` 运行晋升作业且守护全过
- **THEN** 日志输出「生产 vX → vY」预览，生产清单保持不变

#### Scenario: 字节原样晋升签名有效
- **WHEN** 真晋升成功
- **THEN** 生产清单与灰度清单字节一致（未重序列化未重签），已装客户端对其验签通过并按 `auto_enabled` 语义正常进入自动链

#### Scenario: 部署后回读校验
- **WHEN** 晋升部署完成
- **THEN** 作业轮询回读生产清单并与灰度内容比对，一致才判绿；超时仍不一致 MUST 判红
