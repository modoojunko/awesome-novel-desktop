# c-chars-confirm-scope — 任务

## 1. 原型先行（C端用户可见改动）

- [x] 1.1 `docs/design-c/prototypes/character-settings.html`：`syncFoot()`/`charGate()` 改按档位出提示（五态文案见 design.md 表，新增 `gapLine()` 统一缺口卡行）＋已确认态主按钮文案「重新确认」；`headHtml()` 保存态加限定词「这张卡已自动保存」。
      验证：`npm run design:lint` 全绿（严格扫描 31 个文件，0 违规；存量统计只读打印）
- [x] 1.2 `docs/design-c/prototypes/ADJUSTMENTS.md` 追加 `## c-chars-confirm-scope` 段：三条差异（按档位提示 / 已确认态按钮与回执 / 卡头限定词）逐条登记理由，并注明 1 是对原型「恒按完整档」口径的实现侧补正。
      验证：条目已落文末（2026-10-08）

## 2. 实现

- [x] 2.1 `CharacterManager.tsx`：新增 `CharGateHint` 与纯函数 `gateHintOf(list, noProtagonist)`（首档标签从 `GATE_FIELDS` 取，不手抄），经新可选回调 `onGateHintChange` 上抛；缺口取列表响应既有 `gaps`（后端零改动）。
      验证：`src/__tests__/CharacterManager.confirmScope.test.tsx` 3 例纯函数 + 2 例上抛断言全绿
- [x] 2.2 `CharacterManager.tsx`：`.char-save-state` 移入 `.char-side`（主角徽标/合并·删除 同列），四态文案加「这张卡」限定词；卡区上方那行独立保存态删除。
      验证：同上测试「保存态归位卡头」例（断言 closest `.char-head` / `.char-side`，且旧位置无残留）
- [x] 2.3 `SettingsView.tsx`：角色页脚提示改用 `CharGateHint`（五态；档位与 `confirmed` 同源），有缺口走 `.warnline`、齐了走 `.note`；伏笔空表提示与其它面板的行结构不动。
      验证：`src/__tests__/SettingsView.charsFoot.test.tsx` 五态断言全绿；`foreshadow-settings.spec.ts` 7/7 不红
- [x] 2.4 `SettingsView.tsx`：已确认态主按钮与成功回执按保存模型分派（`AUTO_SAVE_PANELS`＝角色/伏笔 →「重新确认」「已重新确认」；表单制面板不动）。
      验证：单测断言按钮文案与 `toast.success("「角色」已重新确认")`；e2e 伏笔 ⑦ 已确认态点「重新确认」恢复徽标

## 3. 测试与回归

- [x] 3.1 新增 vitest：`CharacterManager.confirmScope.test.tsx`（6 例）、`SettingsView.charsFoot.test.tsx`（7 例）。
      验证：两文件 13 例全绿；全量 `npx vitest run` → **109 files / 1269 tests passed**
- [x] 3.2 e2e（隔离栈：容器 `chars-scope-*`、端口 5185/8011/19011、数据目录 worktree `.docker-data/client`，与演示栈零共享；容器内特征串自证「这张卡已自动保存」在 bundle 里）：
      · `settings-forms.spec.ts` 角色用例 ✓（新增：未确认态页脚文案 → 确认后回面板 warn 点名缺口 + 按钮「重新确认」）
      · `foreshadow-settings.spec.ts` 7/7 ✓（⑦ 已确认态按钮改「重新确认」）
      · `design-parity-book.spec.ts`：角色用例为「记录不阻断」态——差异率 **7.157%**（A/B：同 seed 打 main 代码前端 = 7.100%，本次改动基本不改变该差值）；free/modal 四条 12.3%/12.6% 经同法 A/B 复现同值 → **存量红，与本改动无关**（原型 demo-bar 使内容整体下移）
      · `design-parity.spec.ts` + `design-parity-preview.spec.ts`：7 passed / 1 failed（`quota` 2.693%＝已登记的存量光栅漂移）
- [x] 3.3 门禁：`npm run design:lint` 绿；`npx tsc --noEmit` 0 错误；`npx vitest run` 1269/1269；`openspec validate c-chars-confirm-scope --strict` 通过。
      验证：输出摘要如上（3.1/3.3）
