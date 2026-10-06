# c-prompt-pack-hardening

## Why

提示词包现在是**安装期一次性解密、模板以明文落在用户磁盘上**（`{DATA_ROOT}/prompt-pack/v{N}/*.prompt`，
loader 直读），即「任何人都能打开目录拷走我们全部提示词工程」——包括按档位付费才拿到的 pro/max 档。
用户 2026-10-06 拍板：**不做云拼装、拼装仍在本机**，但要把「用 C端 的人逆向解读的成本」抬到
**高于提示词本身的价值**：拿到的应该是密文与二进制，而不是一个能 `grep` 的目录。

## What Changes

- **本地包静态加密**：安装落盘从明文 `.prompt` 改为**密文容器**（`pack.bin`，AES-GCM）；模板明文
  只在内存中出现，不写任何中间文件。
- **本地包密钥绑定机器+用户**：随机会话密钥由 OS 级密钥保护存储保管（Windows DPAPI user-scope /
  macOS Keychain），**不与包同目录明文存放**；把包目录整体拷到别的机器/别的用户 → 解不开。
- **换机/密钥失效的降级**：解不开即按「未装包」走既有重下重装路径；离线时按既有失败矩阵静默
  沿用现态（不弹错、不阻塞写作）。
- **存量迁移**：检测到旧版明文包目录时就地加密转换（保住离线）；转换失败按未装处理重下。
- **暴露面卫生**：模板文本 SHALL NOT 进日志/异常信息/回执文件；不写 `%TEMP%` 中间件。
- **关键解密路径不落字节码**（阶段二，达到用户设定的成本线的关键一步）：
  「包密钥解封＋容器解密」下沉到原生模块（或等效强度手段），使「读懂我们自己的 Python 就能
  调用同一条解密路径」不再成立。
- 新增 spec 级**威胁模型与不承诺项**：防「拷目录/跨机复用/读源码解密」；**不承诺**防内存 dump、
  自建代理抓出口流量、调试器/hook（这些属专业投入，写进 spec 以免反复讨论）。

## Capabilities

### New Capabilities

（无新 capability——防护是既有分发链的强度条款，不另起平行 spec。）

### Modified Capabilities

- `prompt-pack-delivery`：安装落盘形态（明文→密文容器）、本地包密钥的保管与绑定、明文只在内存、
  存量迁移、日志卫生，以及新增「威胁模型与防护强度分级」条款；原有七道校验 / 高水位 / 原子安装 /
  离线自持 / CEK 不落盘 / loader 解析序 / `PromptPackMissing` 契约全部保留不变。

## Impact

- **代码**：`client/backend/prompt_pack/sync.py`（安装段 `_install` 落盘形态、迁移、密钥解封）、
  `client/backend/prompt_pack/__init__.py`（receipt/目录/`verify_file` 适配）、
  `client/backend/prompts/__init__.py`（loader 读路径＝容器解密到内存）、新增本地密钥模块；
  阶段二另加原生模块与其构建链（`client/packaging/build/build.spec` / CI / 本地打包脚本）。
- **数据**：`{DATA_ROOT}/prompt-pack/` 目录格式变化（跨版本共享目录不变）；旧格式自动迁移。
- **依赖**：阶段一零新增依赖（DPAPI 走 ctypes，Keychain 走系统 `security`）；阶段二引入
  编译链（Cython/MSVC 或等效）。
- **不受影响**：S端 换钥契约、CDN 发布链、打包硬切断言、e2e 默认开发态（loader 直读包内目录）
  全部不变；开发/测试态行为与今天逐字节一致。

## Design Impact

无用户可见界面改动：不新增状态、不动文案、不碰两端共享段，无需原型先行。唯一可见行为是
**换机/换用户后首次使用 AI 需联网重下包**（下载期间的既有「写作能力未就绪」锁定卡已覆盖该窗口，
不新增第四种提示面）。
