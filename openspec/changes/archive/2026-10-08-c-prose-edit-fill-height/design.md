## Context

用户 10-08 截图反馈编辑态呼吸框下大片空白。绿框＝`.editor`（TipTap ProseMirror 宿主，680px 版心列，呼吸灯 `.generating` 挂其上），外层 `.editor-wrap` 是 `flex:1; min-height:0; overflow-y:auto` 的滚动容器——容器撑满剩余高度，但列本身没有拉伸语义，高度随内容。

## Goals / Non-Goals

- Goals：编辑态编辑列撑满滚动区剩余高度；短内容无死空白；长文滚动行为不变；查看态不变。
- Non-Goals：不改呼吸灯参数（c-prose-stream-guard 拍板 2s/accent 环）；不改滚动恢复/贴底算法；不动查看态阅读面；不立富文本。

## Decisions

- **flex 链而非 min-height calc**：`.editor-wrap.editing{display:flex;flex-direction:column}`→`.editor-host{flex:1 0 auto;display:flex}`→`.editor{flex:1 0 auto}`。`flex-basis:auto` 保证内容超屏时列高=内容高、照常滚动；不引 vh（大屏 ui-zoom 层会缩放 vh，calc 脆）。
- **包装层挂类而非 `> div` 选择器**：TipTap v3 `EditorContent` 把 rest props 透传到包装 div（dist 实勘），`editor-host` 是稳定钩子；`ZhuqueMarks` 纯 Decorations 无 node view，wrap 内不会有 Portals 兄弟节点。
- **撑满圈定编辑态**：绿框/编辑框只在编辑态存在，查看态阅读面随文走是既有拍板；纯编辑态（未生成）下拉伸无视觉变化——生成开始/结束不跳布局。
- **底部留白 120→36px**：只改编辑态；与顶对称，框沿贴近视窗底；长文滚到底时 36px 即舒适垫。
- **hidden 守卫确认在案**：`.editor-wrap` 靠 `hidden` 属性切页签，新加 `display:flex` 依赖 base.css `[hidden]{display:none!important}` 全局守卫（ProsePane `.ol-top` 同坑前例，守卫已实勘）。

## Risks / Trade-offs

- 编辑态点击正文下方空白从「无效果」变「落焦书写」——撑满的必然结果，属体验改善；无既有交互依赖「点空白失焦」（自动保存走输入防抖）。
- 滚动恢复比例的记录口径在短内容下从「小比值」变 0（scrollHeight==clientHeight）——自愈型数据（下次输入/滚动重记），无持久化格式问题。

## Migration Plan

纯前端布局，无数据迁移；随实现 PR #733 直发（用户截图现场即验收场景）。

## Open Questions

（无——改动当轮已随 #733 合 main=aade5066。）
