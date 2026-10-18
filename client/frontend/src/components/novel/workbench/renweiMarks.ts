/** 人味标注 TipTap 扩展（c-renwei-check）：问题段底色（node decoration）。
 *
 *  与 zhuqueMarks 的边界（两路检测各占一侧、互不读写）：
 *  - 朱雀：黄/红荧光行带＋段尾判定章（label 1/2），入口在左；
 *  - 人味：墨绿批注底色（左竖条＋淡底），右侧边注由 React 覆盖层渲染
 *    （RenweiMarginNotes）——本扩展只管段落标色，不渲染任何文字组件。
 *
 *  机制照抄 zhuqueMarks 的两条实测坑（务必保留）：
 *  1. DecorationSet 必须住 plugin state，只在 meta 事务/docChanged 时重建，
 *     其余事务原样返回同一实例——否则无关重渲会折叠用户选区；
 *  2. 装饰是视图层覆盖，SHALL NOT 进入文档 JSON、撤销历史、自动保存或导出。
 *  段落索引＝非空段序（trim 后非空），与后端 check_prose 切分同口径。
 */
import { Extension } from "@tiptap/core";
import type { Editor } from "@tiptap/core";
import { Plugin, PluginKey, type EditorState } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

interface RenweiStorage {
  /** 需标色的段落（0-based 非空段序）；null＝清空 */
  paras: number[] | null;
}

const REFRESH_META = "renweiMarksRefresh";

export const renweiMarksPluginKey = new PluginKey<DecorationSet>("renweiMarks");

export const RenweiMarks = Extension.create<RenweiStorage>({
  name: "renweiMarks",

  addStorage() {
    return { paras: null } as RenweiStorage;
  },

  addProseMirrorPlugins() {
    const ext = this;
    const buildDecos = (state: EditorState): DecorationSet => {
      const paras = (ext.storage as RenweiStorage).paras;
      if (!paras || paras.length === 0) return DecorationSet.empty;
      const marked = new Set(paras);
      const decos: Decoration[] = [];
      let k = 0;
      state.doc.forEach((node, offset) => {
        if (node.type.name !== "paragraph") return;
        if (node.textContent.trim().length === 0) return; // 空段不计数（与后端切分同口径）
        const idx = k;
        k += 1;
        if (!marked.has(idx)) return;
        decos.push(
          Decoration.node(offset, offset + node.nodeSize, {
            class: "rw-mark",
            title: "这里读起来有点像 AI——右边有改法提示",
          }),
        );
      });
      return DecorationSet.create(state.doc, decos);
    };
    return [
      new Plugin<DecorationSet>({
        key: renweiMarksPluginKey,
        state: {
          init: () => DecorationSet.empty,
          apply(tr, prev, _oldState, newState) {
            if (tr.getMeta(REFRESH_META) || tr.docChanged) return buildDecos(newState);
            return prev;
          },
        },
        props: {
          decorations(state) {
            return renweiMarksPluginKey.getState(state) ?? DecorationSet.empty;
          },
        },
      }),
    ];
  },
});

function sameParas(a: number[] | null, b: number[] | null): boolean {
  if (a === b) return true;
  if (!a || !b) return false;
  return a.length === b.length && a.every((v, i) => v === b[i]);
}

/** 注入/清除段落标色（写 storage＋meta 事务触发重算；未变化不派发＝省一次选区窗口）。 */
export function applyRenweiMarks(editor: Editor, paras: number[] | null) {
  if (editor.isDestroyed) return;
  const st = (editor.storage as { renweiMarks?: RenweiStorage }).renweiMarks;
  if (!st) return;
  if (sameParas(st.paras, paras)) return;
  st.paras = paras;
  editor.view.dispatch(editor.state.tr.setMeta(REFRESH_META, 1));
}
