# settings-done-entry · Design

## 方案（用户拍板：合一）

「设定 8/8」进度行与完成卡**合一**——同一元素两状态，去掉重复的 8/8 与叠卡：

- 日常（done < total）：`.settings-progress` 原样——「设定 7/8」mono 标签＋accent 进度条
- 完成（done === total 且 onGoWrite）：行头加对勾图标，标签变「设定完成 8/8」（ok 绿加粗），追加「全部就绪」徽标；进度条满格转 ok 绿；整块升级为完成卡——ok-soft 底＋ok 描边（圆角 10）；块内追加主 CTA「去写作 →」（唯一行动点）与一行小字「写作时也能回来改设定，不冲突」

状态语言沿 §5：完成=ok 绿（对勾/徽标/满格条）；主 CTA 沿 accent 主按钮档位（状态色不做行动色）。

## 实现要点

- `SettingsView.tsx`：原 `done === total && onGoWrite` 按钮分支删除；`.settings-progress` 容器加条件类 `done`，内部条件渲染 pb-check / pb-badge / done-btn / done-foot（JSX 约 20 行）；CHECK_PATH 对勾沿文件既有常量；箭头内联 SVG（viewBox 24、stroke 2、显式宽高——词汇表口径）
- `book.css` settings-v 段新增 done 变体（`.settings-v .settings-progress.done` ＋ `.pb-check/.pb-badge/.done-btn/.done-foot`）；基线 `.settings-progress` 原样式不动（非 done 态零像素变化）
- ADJUSTMENTS #23：登记词表＋「完成入口不再用普通主按钮」口径；原型转正 `prototypes/settings-done-entry.html`
- 测试：`creation-flow.spec.ts` 设定全确认用例尾部断言完成卡与「去写作」切换；`settings-forms.spec.ts` 文风用例（7/8 态）补「完成卡不出现」断言

## non-goals

7/8「下一步引导条」（可后续另批）；完成卡在中栏镜像；自动跳转写作视图。
