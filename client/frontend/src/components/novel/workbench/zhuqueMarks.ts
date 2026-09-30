/** 朱雀段落标注 TipTap 扩展（c-zhuque-ai-detect）。
 *
 *  Decorations 方案（spec zhuque-workbench「正文段落标注覆盖层」）：
 *  - node decoration 给非空段落挂 `.zq-warn/.zq-err` 底色（label 2=疑似/warn、1=AI/err）；
 *  - widget decoration 在段尾挂 `.zq-mark` 置信度章（contenteditable=false，不进文档）；
 *  - stale（送检指纹 ≠ 当前文档）＝全部装饰置换灰变体（`.zq-stale`/`.zq-mark.stale`）；
 *  - 装饰是视图层覆盖，SHALL NOT 进入文档 JSON、撤销历史、自动保存文本或导出。
 *
 *  注入入口 `applyZhuqueSegments(editor, segments, stale)`：写 storage 后派发一个
 *  meta 事务触发 decorations 重算（ProseMirror 插件状态变更的标准动作）。
 *  段落索引＝非空段序（trim 后非空），与后端切分管道同口径。
 */
import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
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
    return [
      new Plugin<DecorationSet>({
        key: zhuqueMarksPluginKey,
        props: {
          decorations(state) {
            const storage = ext.storage as ZhuqueStorage;
            const segs = storage.segments;
            if (!segs || segs.length === 0) return DecorationSet.empty;
            const decos: Decoration[] = [];
            let k = 0;
            state.doc.forEach((node, offset) => {
              if (node.type.name !== "paragraph") return;
              if (node.textContent.trim().length === 0) return; // 空段不计数（与后端切分同口径）
              const seg = segs[k];
              k += 1;
              if (!seg) return;
              const tone = seg.label === 1 ? "err" : seg.label === 2 ? "warn" : "ok";
              const stale = storage.stale;
              if (stale) {
                decos.push(
                  Decoration.node(offset, offset + node.nodeSize, { class: "zq-stale" }),
                );
                decos.push(markWidget(node, offset, tone, seg.confidence, true));
              } else if (seg.label === 1 || seg.label === 2) {
                decos.push(
                  Decoration.node(offset, offset + node.nodeSize, {
                    class: seg.label === 1 ? "zq-err" : "zq-warn",
                  }),
                );
                decos.push(markWidget(node, offset, tone, seg.confidence, false));
              } else {
                // 人写段：只挂灰章，不着色
                decos.push(markWidget(node, offset, tone, seg.confidence, false));
              }
            });
            return DecorationSet.create(state.doc, decos);
          },
        },
      }),
    ];
  },
});

function markWidget(
  node: { nodeSize: number },
  offset: number,
  tone: "ok" | "warn" | "err",
  confidence: number,
  stale: boolean,
) {
  const el = document.createElement("span");
  el.className = `zq-mark m-${tone}${stale ? " stale" : ""}`;
  el.setAttribute("contenteditable", "false");
  const label = tone === "ok" ? "人写 " : tone === "warn" ? "疑似 " : "AI ";
  el.textContent = `${label}${Math.round(confidence * 100)}%`;
  // 段内末位（nodeSize 含开闭各 1）——side:1 使章落在文本之后
  return Decoration.widget(offset + node.nodeSize - 1, el, {
    side: 1,
    ignoreSelection: true,
  });
}

/** 注入/清除标注（写 storage＋meta 事务触发重算）。stale=true 时全部置换灰变体。 */
export function applyZhuqueSegments(
  editor: Editor,
  segments: ZhuqueSeg[] | null,
  stale = false,
) {
  if (editor.isDestroyed) return;
  const storage = editor.storage as {
    zhuqueMarks?: ZhuqueStorage;
  };
  if (!storage.zhuqueMarks) return;
  storage.zhuqueMarks.segments = segments;
  storage.zhuqueMarks.stale = stale;
  editor.view.dispatch(editor.state.tr.setMeta(REFRESH_META, 1));
}
