# Tasks: brand-owner-line

> 说明：主体口径拍板时实现已随批预置在共享工作区（未提交，与并行在途改动文件不重叠）。
> 1–5 组为已完成事实的登记（apply 阶段为核对），6 组为检视整改，7 组为收尾步骤。

## 1. 原型先行（已完成）

- [x] 1.1 改 6 处原型 © 行为「© 2026 星纬（海口）投资有限公司 · 爱小说」（list/book/model-config/preview 状态条、backup-restore 旧版 pagefoot、home 落地页脚）；`index.html` meta 落款豁免不改。核对：`grep -rn "© 2026 爱小说" docs/design-c/prototypes/*.html` 仅剩 index.html 一条
- [x] 1.2 ADJUSTMENTS.md 追加「版权行加经营主体（© 主体口径统一，2026-09-21）」节（含豁免理由）

## 2. 单源与两端桥（已完成）

- [x] 2.1 `brand/brand.json` 新增 `company: "星纬（海口）投资有限公司"`。核对：`python3 -c "import json;json.load(open('brand/brand.json'))"` 无异常且键值正确
- [x] 2.2 `client/frontend/src/lib/brand.ts`：导出 `companyName`，`copyrightLine` = `© {年} {companyName} · {BRAND.name}`
- [x] 2.3 `server/frontend/src/constants/brand.ts`：导出 `companyName`，`brandCopyright()` = `© {年} {companyName} · {brandFull()}`；注释明确不参与运行时 brandName 覆盖

## 3. Windows 发布者（已完成）

- [x] 3.1 `client/packaging/build/build.spec`：win32 分支生成 `version_info.txt`（CompanyName/LegalCopyright=company，ProductName/FileDescription 取 name/nameEn，FileVersion 取 APP_VERSION>git describe>0.0.0），缺 company 键 `SystemExit` 拒构建；传 `EXE(version=…)`，非 Windows 不触达
- [x] 3.2 `installer.iss`：`MyAppPublisher "星纬（海口）投资有限公司"`＋「唯一手写同步点」「UTF-8 无 BOM 约束」注释
- [x] 3.3 `.github/workflows/client-package.yml` Build app 步骤注入 `APP_VERSION: ${{ github.ref_name }}`；`.gitignore` 排除 `client/packaging/build/version_info.txt`

## 4. 测试断言（已完成）

- [x] 4.1 `client/frontend/e2e/statusbar.spec.ts` 断言升级 `/© \d{4} 星纬（海口）投资有限公司 · 爱小说/`
- [x] 4.2 `server/frontend/e2e/tests/landing.spec.ts` 页脚断言升级 `/© \d{4} 星纬（海口）投资有限公司 · 爱小说 · AI Novel/`

## 5. 门禁回归（已完成，结论记录）

- [x] 5.1 双端类型：C端 `npx tsc --noEmit` 通过；S端 `npm run typecheck`（vue-tsc --noEmit）通过
- [x] 5.2 C端 `npm run design:lint` 通过（仅存量分布观察输出，无阻断）；`DESIGN_PARITY=1` 跑 4 个 parity spec：9 过 5 失败，diff 图归因失败红块集中在并行在途工作改的中栏版式（空态卡/工作台），状态条区域为底噪，且带新文案的 9 个场景全过——本改动 parity 干净（在途合并后自然消解）
- [x] 5.3 C端 vitest 全量 714/714；`brand.py` 实读新 brand.json 白名单键位不漂移
- [x] 5.4 受影响 e2e：重建 `client-frontend` 镜像后 statusbar.spec 10/10；S端 landing 页脚用例过；C端 全量 e2e 118 过 0 挂（17 skipped＋1 did not run 为 workbench-features 族，单跑复现为 createNovel 弹回登录的既有失败，与本次无因果——后端容器为旧镜像，不含本次任何代码）
- [x] 5.5 PyInstaller 6.22.3 真加载器（打桩 win32api）解析生成的版本文件：全部字段落位、`toRaw()` 732 字节正常
- [x] 5.6 Inno 编码事实核验：官方 changelog 6.3.0 原文确认 `.iss` 无 BOM UTF-8 支持且为推荐形态（design.md D5）

## 6. 检视整改（后端架构师 09-21 检视：裁决通过，P2 三条应修）

- [x] 6.1 【P2-2】版本文件模板零转义：`build.spec` 生成 version_info.txt 的 f-string 直插 json 值，值含 `'`/`\` 时产出非法 Python（eval 报 SyntaxError 难定位）。改 `{值!r}` 生成合法字面量＋三值 `isinstance(str)` 门禁。核对：临时构造含单引号的 company 跑生成逻辑，真加载器解析成功
- [x] 6.2 【P2-1】数字版本位污染：`re.findall(r'\d+')` 取前 4 组会把哈希数字/PR 号灌进 filevers（如 `0.22-13-gdfceb17d-dirty` → (0,22,13,17)）。改为只取首个点分数字前缀（`re.match(r'\d+(?:\.\d+)*', _ver)`）按 `.` 切分补零，每段 clamp 0–65535（顺带覆盖 WORD 溢出）。核对：`v0.22-13-gdfceb17d-dirty`→(0,22,0,0)（点分前缀止于 0.22，尾巴不进位）、`123/merge`→(123,0,0,0)、纯哈希→(0,0,0,0)、`v99999.1`→(65535,1,0,0)
- [x] 6.3 【P2-3】installer.iss 字面量防漂移零自动化：加一条 pytest（读 brand.json 的 company 与 installer.iss 的 MyAppPublisher 字面量逐字比对）或 client-package.yml 加 grep 断言步。核对：手工改错一侧行，测试/CI 红
- [x] 6.4 【P3-1 顺带】company 门禁报错文案补「（含 macOS 构建前置校验）」；`_brand["name"]`/`_brand["nameEn"]` 裸下标改同型显式报错
- [x] 6.5 【缺口登记】macOS .app 的 Info.plist 无版权/主体元数据（NSHumanReadableCopyright），mac 签名身份与公司主体无关联——超出本 change（installer-release 为 Windows-scoped），开独立 change 承接
- [x] 6.6 【备忘不改】CI 与 build.spec 清洗集差 `+`（更新检测 `_VERSION_RE` 纯数字点分，两侧分叉无消费方）；build.bat 本地路径 v 前缀双写（既有行为，CI 发布路径不受影响）

## 7. 收尾（剩余）

- [ ] 7.1 提交：按文件域分批或单 commit（brand 单源＋两端桥／打包层＋CI／原型＋ADJUSTMENTS＋两 e2e 断言＋openspec 工件），开 PR；注意与并行在途改动同树不同文件，勿 `git add -A`
- [ ] 7.2 CI 核对：PR 触发 `client-package.yml`，Windows job 绿＝Inno 编译＋版本资源真机验证；下载 artifact 在 Windows 属性页/任务管理器核对发布者署名（端到端终验）
- [ ] 7.3 与 relicense-proprietary 对账：其 tasks 2.1 的 `MyAppPublisher=星纬（海口）投资有限公司` 已被本 change 提前满足（apply 时核对即可），`MyAppURL` 换官网与 `LicenseFile` 仍归该 change
- [ ] 7.4 归档：specs sync（brand-identity 三 MODIFIED＋installer-release 一 ADDED 落 `openspec/specs/`），归档总结记桌面知识库
