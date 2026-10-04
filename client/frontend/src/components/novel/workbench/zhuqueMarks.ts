/** 朱雀段落标注 TipTap 扩展（c-zhuque-ai-detect；带化 c-zhuque-mark-band）。
 *
 *  Decorations 方案（spec zhuque-workbench「正文段落标注覆盖层」）：
 *  - 连续同判定的非空段聚合为**标注带**：node decoration 给带内每段挂
 *    `.zq-warn/.zq-err` 荧光笔式底色（label 2=疑似/warn、1=AI/err）＋`title`
 *    悬停提示（判定词＋置信度，不常驻）；
 *  - widget decoration 只在**带尾段**挂一个 `.zq-mark` 判定词章（人写段零渲染）；
 *  - stale（送检指纹 ≠ 当前文档）＝现状语义：段落只挂 `.zq-stale`（无底色）、
 *    带尾章置换灰变体（`.zq-mark.stale`）；
 *  - 装饰是视图层覆盖，SHALL NOT 进入文档 JSON、撤销历史、自动保存文本或导出。
 *
 *  带分组＝数组相邻同 label（与 doc 遍历位置消费同轨）；连续性由后端契约保证
 *  （align_segments 逐段输出 paragraph_index 连续 0..N-1，zhuque-detection 条款
 *  ＋test_zhuque.py 双钉）。空段天然不在 segments，不打断带的聚合。
 *
 *  注入入口 `applyZhuqueSegments(editor, segments, stale)`：写 storage 后派发一个
 *  meta 事务触发 decorations 重算（ProseMirror 插件状态变更的标准动作）。
 *  段落索引＝非空段序（trim 后非空），与后端切分管道同口径。
 *
 *  DecorationSet 必须住 plugin state（apply 里只在 meta 事务 / docChanged 时重建，
 *  其余事务原样返回同一实例）：decorations prop 若每次求值都现算新集合，TipTap
 *  React 层任一无关重渲（setOptions→view.setProps→updateState）都会让 PM 误判
 *  文档变了，走 selectionToDOM 把浏览器刚做的选区/光标折叠掉——实测症状＝
 *  标注在场时首次双击选词、点选定位、拖拽全部被吞（缺陷自 #617 初版即存在，
 *  非 c-zhuque-mark-band 引入；回归钉子见 zhuqueWorkbench.test.tsx 身份稳定例）。
 */
import { Extension } from "@tiptap/core";
import { Plugin, PluginKey, type EditorState } from "@tiptap/pm/state";
import type { Editor } from "@tiptap/core";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

export interface ZhuqueSeg {
  paragraph_index: number;
  label: 0 | 1 | 2; // 0=人工 1=AI 2=疑似
  confidence: number;
}

interface ZhuqueStorage {
  segments: ZhuqueSeg[] | null;
  stale: boolean;
}

const REFRESH_META = "zhuqueMarksRefresh";

export const zhuqueMarksPluginKey = new PluginKey<DecorationSet>("zhuqueMarks");

/** 带分组：数组相邻同 label 聚合，返回各带末位的 paragraph_index 集合。 */
export function bandTails(segs: ZhuqueSeg[]): Set<number> {
  const tails = new Set<number>();
  for (let i = 0; i < segs.length; i += 1) {
    if (i + 1 === segs.length || segs[i + 1].label !== segs[i].label) {
      tails.add(segs[i].paragraph_index);
    }
  }
  return tails;
}

export const ZhuqueMarks = Extension.create<ZhuqueStorage>({
  name: "zhuqueMarks",

  addStorage() {
    return {
      segments: null,
      stale: false,
    } as ZhuqueStorage;
  },

  addProseMirrorPlugins() {
    const ext = this;
    const buildDecos = (state: EditorState): DecorationSet => {
      const segs = (ext.storage as ZhuqueStorage).segments;
      if (!segs || segs.length === 0) return DecorationSet.empty;
      const stale = (ext.storage as ZhuqueStorage).stale;
      const tails = bandTails(segs);
      const decos: Decoration[] = [];
      let k = 0;
      state.doc.forEach((node, offset) => {
        if (node.type.name !== "paragraph") return;
        if (node.textContent.trim().length === 0) return; // 空段不计数（与后端切分同口径）
        const seg = segs[k];
        k += 1;
        if (!seg) return;
        if (seg.label !== 1 && seg.label !== 2) return; // 人写段：静默（无底色无章）
        if (stale) {
          decos.push(
            Decoration.node(offset, offset + node.nodeSize, { class: "zq-stale" }),
          );
        } else {
          const cls = seg.label === 1 ? "zq-err" : "zq-warn";
          const word = seg.label === 1 ? "AI" : "疑似";
          decos.push(
            Decoration.node(offset, offset + node.nodeSize, {
              class: cls,
              title: `${word} ${Math.round(seg.confidence * 100)}%`,
            }),
          );
        }
        if (tails.has(seg.paragraph_index)) {
          decos.push(markWidget(node, offset, seg.paragraph_index, seg.label, stale));
        }
      });
      return DecorationSet.create(state.doc, decos);
    };
    return [
      new Plugin<DecorationSet>({
        key: zhuqueMarksPluginKey,
        state: {
          init: () => DecorationSet.empty,
          apply(tr, prev, _oldState, newState) {
            // 只在标注变更（meta）或文档变化（位置重排）时重建；其余事务原样
            // 返回同一实例——身份稳定是 matchesNode 免误判的前提
            if (tr.getMeta(REFRESH_META) || tr.docChanged) {
              return buildDecos(newState);
            }
            return prev;
          },
        },
        props: {
          decorations(state) {
            return zhuqueMarksPluginKey.getState(state) ?? DecorationSet.empty;
          },
        },
      }),
    ];
  },
});

function markWidget(
  node: { nodeSize: number },
  offset: number,
  paragraphIndex: number,
  label: 1 | 2,
  stale: boolean,
) {
  // 段内末位（nodeSize 含开闭各 1）——side:1 使章落在文本之后。
  // toDOM 必须是**函数**＋key 须稳定：元素形态 widget 的 `!toDOM.parentNode`
  // 恒假（元素总挂着父节点），placeWidget 永不复用——每次重建（按键/重检）
  // 都整颗重造 DOM 且装饰集值不等，matchesNode 失配 → selectionToDOM 折叠
  // 用户选区（与头注同一症状族）。函数形态＋key 命中 WidgetType.eq 后跨重建复用。
  return Decoration.widget(
    offset + node.nodeSize - 1,
    () => {
      const el = document.createElement("span");
      el.className = `zq-mark m-${label === 1 ? "err" : "warn"}${stale ? " stale" : ""}`;
      el.setAttribute("contenteditable", "false");
      el.textContent = label === 1 ? "AI" : "疑似";
      return el;
    },
    {
      side: 1,
      ignoreSelection: true,
      key: `zq-${paragraphIndex}-${label}${stale ? "-stale" : ""}`,
    },
  );
}

/** 注入/清除标注（写 storage＋meta 事务触发重算）。stale=true 时全部置换灰变体。
 *  幂等守卫：segments/stale 未变化时不派发——冗余 meta 事务会让装饰集与视图
 *  值不等（见 markWidget key 注释），白吃一次 selectionToDOM 窗口。 */
export function applyZhuqueSegments(
  editor: Editor,
  segments: ZhuqueSeg[] | null,
  stale = false,
) {
  if (editor.isDestroyed) return;
  const storage = editor.storage as {
    zhuqueMarks?: ZhuqueStorage;
  };
  const st = storage.zhuqueMarks;
  if (!st) return;
  if (st.segments === segments && st.stale === stale) return;
  st.segments = segments;
  st.stale = stale;
  editor.view.dispatch(editor.state.tr.setMeta(REFRESH_META, 1));
}
