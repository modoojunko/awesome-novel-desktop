# c-character-library — 实现任务

## 1. 原型先行（已完成，偏差登记）

- [x] 原型五场景已产出并过评审：`docs/design-c/drafts/ai-novel-c端-角色库-原型.src.html`（build/check 脚本同目录，自检全绿：宿主逐字 6 份／类溯源 85 个／黑名单零命中）；设计说明 `docs/design-c/drafts/ai-novel-c端-角色库-设计说明.md`；四方评审汇总同目录。
- [x] 基线登记：`ADJUSTMENTS.md` 已登记「角色库（c-character-library）——新增页，不设 parity 基线」（design:check 豁免理由在案）。

## 2. 后端：数据与域

- [x] `models/character_library.py`：主表＋`character_library_blobs`＋部分唯一索引；已注册 `models/__init__.py`；加列纪律进 db-generation delta。
- [x] 头像档位复用 `normalize_image("avatar")`（512/96 LANCZOS WebP q85，严于 spec 上限）；收录直拷 blob、用到新书同管线写入 ImageAsset；无图姓字块。
- [x] `library/service.py`：list_all/create/update/delete/collect（幂等）/sync（source_gone→410）/apply_to_book（撞名后缀≤5、主角落配角留痕、cog＋头像整卡）/random_name（AI＋兜底恒 200）。/create/update(整卡)/delete/collect_from_book（幂等，provenance；空名兜底「未命名#序号」；`ON CONFLICT DO NOTHING` 或捕 IntegrityError 回查）/sync_from_book（PULL 书域格，源失效可读错）/apply_to_book（**扩 create_character 可选 cog(COG_KEYS 白名单)＋avatar(→ImageAsset+Blob 同事务)**；撞名主体先截断留后缀位再「（角色库{n}）」重试≤5；主角遇书内已有主角落配角＋回执）/random_name（AI＋本地兜底恒 200，不挂档位门）。读卡投影白名单组装（禁 model_dump 直出）。
- [x] `library/router.py` 九操作全落地：静态段前置；头像端点 ETag→304＋Cache-Control；带书端点自校验归属；LibraryError→HTTP 映射；logger 留痕。
- [x] AI 起名路径已实现并兜底恒 200（TestRandomName 钉）；**prompts 私仓模板待随下批提示词包发布**（跨仓；无模板兜底独立成立）。

## 3. 后端：备份与迁移

- [x] 配置包 v8：导出段＋二进制头像条目；`parse_package` 读 zip 头像字节（不改 `_restore_config` 签名）、落卡按 id 幂等、sha256 校验、缺文件 warning；`FORMAT_VERSION=8` 断言同批改；往返用例绿。
- [x] `_manifest_rows` 加 `library_total`（缺表→0，两例测试）；前端第三块仅>0 渲染（`useLegacyDb` 类型同批）。
- [x] 回归：`test_character_library.py` 14 例（CRUD/收录幂等/同步三态/撞名/主角降级/随机兜底/备份 v8 往返/告知卡计数）；整库迁移演练待发车前跑（引擎「注册即列交集」保证）；同机回导 provenance 失效→同步 410 可读提示。

## 4. 前端：页面与交互

- [x] 4a：路由＋菜单第三项＋`toolsMenu.test`（三项断言＋导航分支）同批。
- [x] 4b：`libraryApi.ts`＋`queryKeys.characterLibrary`＋`useCharacterLibrary`（普通 useQuery）；头像鉴权 fetch＋objectURL 缓存；列表加载/失败重试/双空态；写后失效同源 key；同步用返回卡回填。
- [x] 4c：`design/library.css`＋`main.tsx` 引入；base.css 零改动。
- [x] 4d：页头＋统计/四组筛选 AND/多词 AND＋NFKC 同源高亮＋命中回落行/排序两档/双视图（视图进 localStorage）/容器 .main 内档。**筛选进 URL searchParams 未做**（非 spec 硬要求，挂账）。
- [x] 4e：`LibraryAvatar`（不走 ImageThumb）；定位 pill 四档既有组合（不新增实底胶囊）；档号/人设两行/语言特征/诞生于；article role=button＋Enter/Space；悬停浮现＋触屏常显。
- [x] 4f：Modal width=600＋内容区滚动；全字段（认知 30 格直取共享常量）；书源卡同步钮；删除同层显式确认（明示复制语义）；AI 单钮只填名字年龄；全字段 aria-label。
- [x] 4g：书内导入清单（v1 逐张、开关默认勾选）；「用到新书」选书（现存书单选）。**「新建一本」入口未做**（挂账：先建书再从该书角色页导入，不阻塞主线）。
- [x] 4i：告知卡第三块（仅 >0 渲染）。
- [x] 4h：按钮行第 4 钮「从角色库导入」；卡操作 `CollectToLibrary`（收入/同步两态，queryClient 单例取数不依赖 Provider）。

## 5. 门禁与回归

- [x] 后端 pytest：`test_character_library.py` 14 例全绿（CRUD/收录幂等/同步三态/撞名后缀/主角降级/随机兜底/备份 v8 往返/告知卡计数）；全量回归 **2867 passed**（2 例存量红经干净 main A/B 定罪：chapter_writer 样式样例单跑亦红、style distill 顺序污染）。
- [x] 前端 vitest：全仓 **149 文件 1874 例全绿**，覆盖率契约四维 100%（`characterLibrary.test.tsx` 13 例＋`…Branches` 10＋`…Coverage` 6＋`…Degenerate` 10＋`libraryApi` 8，覆盖四组筛选/多词高亮同源/双视图/CRUD/空态/随机两格/键盘可达/异常兜底）。
- [x] e2e：`e2e/character-library.spec.ts` UI 桩 **3/3 绿**（菜单→库页→筛选/双视图→新建保存→用到新书参数断言）；拆书收录腿与书内「收入角色库」往返归 `c-charlib-deconstruct-exit` 的 e2e（本单不挂跨单依赖），书内落卡由后端 apply 用例覆盖。
- [x] 门禁①原型基线按 ADJUSTMENTS 豁免；②design:check 不覆盖新页已登记；③8 个新文件入覆盖率契约（四维 100%）；④toolsMenu.test 更新；⑤`e2e/character-library.spec.ts` UI 桩 3/3 绿（书内落卡由后端用例覆盖）。
- [x] 门禁实测：tsc 绿；build 绿（check-inline-colors/legacy-colors）；design:lint 唯一红＝preview.html ⚠（存量，HEAD 同存在）；vitest 1874 全绿＋覆盖率四维 100%；e2e 3/3。S端零改动。
- [x] 文案核对过；术语表条目归档时同批补。
