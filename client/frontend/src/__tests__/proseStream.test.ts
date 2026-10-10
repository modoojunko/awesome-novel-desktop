// 流式写入复现（fix/stream-mirror-normalize 后续）：appendChunk 增量镜像＋
// 段落 split 位移（+2）在真实 TipTap 编辑器上的端到端行为——
// 回归钉：多 chunk 带 \n\n 流式后，文档必须与后端归一文本逐字一致、零碎片
// c-prose-regen-replace：另钉「替换写」链——生成前整档清除，终稿＝生成物
import { describe, expect, it, vi } from "vitest";
import { Editor } from "@tiptap/core";
import Document from "@tiptap/extension-document";
import Paragraph from "@tiptap/extension-paragraph";
import Text from "@tiptap/extension-text";
import { UndoRedo } from "@tiptap/extensions";
import {
  docToProse,
  linesToParagraphs,
  normalizeStreamedProse,
  proseDelta,
  proseToDoc,
} from "@/components/novel/workbench/proseDoc";

function makeEditor(withHistory = false) {
  return new Editor({
    extensions: [
      Document,
      Paragraph,
      Text,
      // newGroupDelay 0：真实链里「清空」与「写回」隔着整段流式时长（≫500ms 默认
      // 分组窗），恒为两个历史条目；测试里两者只隔毫秒，须关掉合并才同构
      ...(withHistory ? [UndoRedo.configure({ newGroupDelay: 0 })] : []),
    ],
    content: "",
  });
}

/** 复刻 ProsePane 的三段式：startStream 垫段 → appendChunk 增量镜像 → finishStream 重排 */
function simulate(chunks: string[]) {
  const editor = makeEditor();
  const streamReceivedRef = { current: "" };
  const streamInsertedLenRef = { current: 0 };
  let streamPos = 0;
  let streamStart = 0;

  // startStream（对齐 ProsePane）：size===0 垫段取 1；否则非续写＝末段内（size-1）
  if (editor.state.doc.content.size === 0) {
    const tr = editor.state.tr;
    const para = editor.state.schema.nodes.paragraph?.create();
    if (para) tr.insert(0, para);
    editor.view.dispatch(tr);
    streamPos = 1;
  } else {
    streamPos = editor.state.doc.content.size - 1;
  }
  streamStart = streamPos;

  const appendChunk = (chunk: string) => {
    if (!chunk) return;
    streamReceivedRef.current += chunk;
    const full = normalizeStreamedProse(streamReceivedRef.current);
    const delta = proseDelta(full, streamInsertedLenRef.current);
    if (!delta) return;
    const { state, view } = editor;
    const tr = state.tr;
    let cur = streamPos;
    const lines = delta.split("\n");
    lines.forEach((line, i) => {
      if (line) {
        tr.insertText(line, cur, cur);
        cur += line.length;
      }
      if (i < lines.length - 1) {
        tr.split(cur);
        cur += 2; // 段落边界占 2 个位置（闭合+开启）——与 ProsePane 修复同步
      }
    });
    view.dispatch(tr);
    streamPos = cur;
    streamInsertedLenRef.current = full.length;
  };

  for (const c of chunks) appendChunk(c);

  // finishStream：删流式区间 → 重插归一后的 done 文本
  const fullText = normalizeStreamedProse(streamReceivedRef.current);
  const end = streamPos;
  if (end > streamStart) {
    const tr = editor.state.tr.delete(streamStart, end);
    editor.view.dispatch(tr);
  }
  if (fullText.trim()) {
    editor
      .chain()
      .insertContentAt(streamStart, linesToParagraphs(fullText))
      .run();
  }
  return { doc: docToProse(editor.getJSON()), expected: fullText, editor };
}

function tokenize(text: string, sizes: number[]): string[] {
  // 按 token 尺寸切片（模拟真实 provider 的不规则分块），\n 独立成 token
  const out: string[] = [];
  let i = 0;
  let k = 0;
  while (i < text.length) {
    const n = sizes[k % sizes.length];
    k += 1;
    out.push(text.slice(i, i + n));
    i += n;
  }
  return out;
}

describe("流式增量镜像复现", () => {
  it("正常分块：流式后文档与后端归一文本一致", () => {
    const text = "夜禁的钟声敲过第三下。\n林野走在队伍最外侧。\n「闭嘴，当值。」\n巷口的风带着河腥味。";
    const { doc, expected } = simulate(tokenize(text, [3, 5, 2]));
    expect(doc).toBe(expected);
  });

  it("模型发段间空行：流式即收敛，不产生空段落", () => {
    const text = "第一段。\n\n第二段。\n\n\n第三段。";
    const { doc, expected } = simulate(tokenize(text, [2, 4, 1]));
    expect(doc).toBe(expected);
    expect(doc).not.toContain("\n\n");
  });

  it("尾部换行 + 空 delta 分块", () => {
    const text = "第一段。\n第二段。";
    const chunks = ["第一段。\n", "", "\n", "第二段。"];
    const { doc, expected } = simulate(chunks);
    expect(doc).toBe(expected);
    expect(expected).toBe(text);
  });
});

describe("段落 split 位移回归（多 chunk 碎片化）", () => {
  it("长文本多 chunk：doc 与归一文本逐字一致，无单字碎片行", () => {
    const text = [
      "夜禁的钟声敲过第三下，旧街区的煤气灯灭了一半。",
      "林野走在队伍最外侧，巡段是哨站分给他的那一段最烂的。",
      "「我说野子，」阿蓟压着嗓子，「北岸那批私活，就差你一个——」",
      "「闭嘴，当值。」",
      "巷口的风带着河腥味。他不怕冷，可风灌进袖口时，那道旧咬痕总有些发痒。",
    ].join("\n");
    const { doc, expected } = simulate(tokenize(text, [1, 2, 3, 5, 2, 4]));
    expect(doc).toBe(expected);
    // 无单字碎片行
    for (const line of doc.split("\n")) {
      expect(line.length).toBeGreaterThan(1);
    }
  });

  it("finishStream 重排后与流式终态一致（零跳变）", () => {
    const text = "第一段开头。\n第二段跟上来，话没说完。\n第三段收尾。";
    const { doc, expected } = simulate(tokenize(text, [2, 3, 1, 4, 2]));
    expect(doc).toBe(expected);
    expect(expected).toBe(text);
  });
});

// ── c-prose-regen-replace：生成＝替换本章正文（ProsePane.startStream 同链复现）──
describe("替换写（c-prose-regen-replace）", () => {
  /** 替换链复现：预置旧正文 → 整档清除（入撤销史）→ 垫段 → 流式 → finish 重排 */
  function simulateReplace(oldProse: string, chunks: string[]) {
    const editor = makeEditor(true);
    // 章正文投影走 JSON（与 ProsePane proseToDoc 同源；setContent 字符串会按
    // HTML 解析、把 \n 吞成同段空格）
    editor.commands.setContent(proseToDoc(oldProse));
    const before = docToProse(editor.getJSON());

    // startStream：流式标记后整档清除（ProsePane 里该事务入撤销史）。
    // prosemirror 删除全域会留一个空段作保底结构——它恰是流式脚手架，
    // 与 ProsePane 的 size===0 垫段守卫同款分流：非零文档不再垫段
    editor.view.dispatch(
      editor.state.tr.delete(0, editor.state.doc.content.size),
    );
    let pos: number;
    if (editor.state.doc.content.size === 0) {
      const para = editor.state.schema.nodes.paragraph.create();
      const padTr = editor.state.tr.insert(0, para);
      padTr.setMeta("addToHistory", false);
      editor.view.dispatch(padTr);
      pos = 1;
    } else {
      pos = editor.state.doc.content.size - 1; // 空段内
    }
    const start = pos;

    const streamReceived = { current: "" };
    const insertedLen = { current: 0 };
    for (const chunk of chunks) {
      streamReceived.current += chunk;
      const full = normalizeStreamedProse(streamReceived.current);
      const delta = proseDelta(full, insertedLen.current);
      if (!delta) continue;
      const tr = editor.state.tr;
      // chunk 事务不入史（与 ProsePane appendChunk 同款）
      tr.setMeta("addToHistory", false);
      let cur = pos;
      delta.split("\n").forEach((line, i, arr) => {
        if (line) {
          tr.insertText(line, cur, cur);
          cur += line.length;
        }
        if (i < arr.length - 1) {
          tr.split(cur);
          cur += 2;
        }
      });
      editor.view.dispatch(tr);
      pos = cur;
      insertedLen.current = full.length;
    }

    // finishStream：删流式区间（不入史）→ 整段写回（入史）；正文终态＝生成物
    const generated = normalizeStreamedProse(streamReceived.current);
    if (pos > start) {
      const tr = editor.state.tr.delete(start, pos);
      tr.setMeta("addToHistory", false);
      editor.view.dispatch(tr);
    }
    if (generated.trim()) {
      editor
        .chain()
        .insertContentAt(start, linesToParagraphs(generated), {
          updateSelection: false,
        })
        .run();
    }
    return { editor, before, generated };
  }

  it("已有正文章生成：旧正文清空，终稿＝本次生成物（不再追加）", () => {
    const text = "夜禁的钟声敲过第三下。\n林野走在队伍最外侧。";
    const { editor, before, generated } = simulateReplace(
      "旧的一段。\n旧的另一段。",
      tokenize(text, [3, 5, 2]),
    );
    expect(before).toBe("旧的一段。\n旧的另一段。");
    const doc = docToProse(editor.getJSON());
    expect(doc).toBe(generated);
    expect(doc).toBe(text);
    expect(doc).not.toContain("旧的一段");
  });

  it("一次撤销回到空稿（旧正文的找回路径＝版本历史，产品口径）", () => {
    const { editor } = simulateReplace(
      "旧的一段。\n旧的另一段。",
      tokenize("新生成的第一段。\n新生成的第二段。", [2, 4, 1]),
    );
    editor.commands.undo();
    expect(docToProse(editor.getJSON())).toBe("");
    // 深层撤销跨越生成段的回放不构成找回承诺（untracked 流式事务夹层），
    // 不在此钉——「清空与找回」的产品口径见 RegenConfirmModal 文案与 spec delta。
  });
});
