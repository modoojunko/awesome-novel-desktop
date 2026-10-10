# c-char-batch-import — 任务

## 1. 原型先行（C端 硬性流程）

- [x] 1.1 `docs/design-c/prototypes/character-settings.html` 补「批量添加」按钮＋弹层（下载/选择文件、预览表、行级状态徽标、字段说明折叠块、建卡中 busy、结果回执含撤销出口），交互抄 drafts 原型；`ADJUSTMENTS.md` 登记每处偏差
- [x] 1.2 `npm run design:lint` + `design:check` 过（原型同步后）

## 2. 后端

- [x] 2.1 `character_service.create_character` 扩参 `aliases`/`dossier`：新增校验器（dossier 白名单八格/逐格 strip+[:300]/非法 400 点名；aliases ≤20×[:50]/空串丢）；name 补 [:50]；合并 `{**prefill_dossier, **dossier}`；router 透传
- [x] 2.2 pytest：全字段落卡可读回／非法键点名 400／非对象与非字符串值 400／aliases clamp（25→20、超长截 50、空串丢）／name clamp 50 不撞唯一键／prefill×dossier 同格 dossier 胜／老载荷（仅 prefill）回归不变

## 3. 前端

- [x] 3.1 引入 xlsx（CDN tarball 0.20.x）＋ dynamic import 独立 chunk；`package.json`/锁文件留痕
- [x] 3.2 `lib/characterImport.ts`：列头归一化映射（中/英/变体）、`sheet_to_json raw:false` 行解析、normItem/rowStatus（注入库内重名集合与已有主角，不读全局）、模版双 sheet 构建、`IMPORT_FIELD_GUIDE` 常量
- [x] 3.3 `BatchAddModal.tsx`：文件选择（护栏：扩展名/10MB/100 行、GBK 回退）→ 预览表（行内改/删、示例行黄、重名黄、多主角红、解析错误红条禁确认）→ 串行建卡（409 计跳过、停批文案、busy/进度）→「撤销本次全部」→ 折叠说明块（渲染 IMPORT_FIELD_GUIDE）→ 草稿保留
- [x] 3.4 `CharacterManager.tsx` 接线：「批量添加」按钮（文案避让 e2e）＋编排（reloadList、选中第一张新卡、建卡前 flush 保存队列）；`charactersApi.create` 扩参透传
- [x] 3.5 登记 `coverage-contract.ts`；v8 ignore 薄壳（文件对话框/指针）带理由注释
- [x] 3.6 vitest：characterImport 矩阵（列头中英混排乱序/变体/缺名字列报错；行级全套；raw:false 数字字符串化；BOM+GBK；护栏；**模版生成→SheetJS 回读＝IMPORT_FIELD_GUIDE 同源契约**）；BatchAddModal（预览/编辑重算/建卡请求序列携 aliases+dossier/409 跳过/停批/撤销 DELETE 序列/草稿保留/折叠块同源）

## 4. e2e（独立栈）

- [x] 4.1 下载模版（捕获 download，Node 侧 SheetJS 回读断言双 sheet/中文列头/示例行）
- [x] 4.2 导入 happy path：造 fixture→上传→预览→建卡→断言列表末尾/自动选中/别名与八格落库→撤销全清→列表还原
- [x] 4.3 同一文件重复导入第二次全跳过（幂等钉）
- [x] 4.4 存量 `settings-forms.spec.ts` 角色用例原样跑绿（选择器/文案零变化确认）

## 5. 收尾

- [x] 5.1 `tsc --noEmit`、`design:check`、后端 pytest、前端 vitest 全绿
- [ ] 5.2 真机冒烟（用户侧验收）：Excel/WPS 实填一份模版导入（含 GBK CSV 与纯数字年龄）；自动化等价面已由 e2e 4.1-4.4 覆盖（xlsx 回读/GBK 拒码回退单测/护栏单测）
