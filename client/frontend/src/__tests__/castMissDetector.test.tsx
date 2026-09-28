// 名单缺人探测（c-character-intro 6.x 通用逻辑）：有卡角色（含别名）被本章文字
// 点名但不在出场名单——确定性文本匹配（零 AI），每章查看/编辑都在场；主角置顶；
// 「加入」走 form.chars＋onPatch（3s 自动保存链）；「忽略」按章会话内记忆。
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import OgPane from "@/components/novel/workbench/OgPane";
import { EMPTY_OG_FORM, type OgForm } from "@/components/novel/workbench/chapterForm";

const toastState = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("@/lib/toast", () => ({ toast: toastState }));

function makeForm(over: Partial<OgForm> = {}): OgForm {
  return {
    ...EMPTY_OG_FORM,
    summary: "夜禁后旧街区，林野随上司巡逻遭伏击",
    plots: [
      "巷口又见袭击：抓痕三道，深浅与上一案一致",
      "老药铺取止血散：银铎认出了药渣里的银粉",
    ],
    ...over,
  };
}

function renderPane(opts: {
  form?: OgForm;
  characterNames?: string[];
  protagonistName?: string;
  label?: string;
  onPatch?: (p: Partial<OgForm>) => void;
}) {
  const onPatch = opts.onPatch ?? vi.fn<(p: Partial<OgForm>) => void>();
  render(
    <OgPane
      form={opts.form ?? makeForm()}
      characterNames={opts.characterNames ?? ["林野", "阿蓟", "银铎"]}
      protagonistName={opts.protagonistName ?? "林野"}
      label={opts.label ?? "第02章 · 夜巡"}
      editing={false}
      loading={false}
      onPatch={onPatch}
      gaps={[]}
      confirmed={false}
      saving={false}
      onStartEdit={vi.fn()}
      onCancelEdit={vi.fn()}
      onGapClick={vi.fn()}
      onSaveDraft={vi.fn()}
      onConfirm={vi.fn()}
      onGoWrite={vi.fn()}
    />,
  );
  return onPatch;
}

describe("名单缺人探测（每章通用）", () => {
  it("剧情点名、但不在出场名单的有卡角色→就近软提示；主角置顶", () => {
    renderPane({
      form: makeForm({ chars: "阿蓟" }), // 林野/银铎 被点名但不在名单
      characterNames: ["林野", "阿蓟", "银铎"],
      protagonistName: "林野",
    });
    expect(screen.getByTestId("cast-missing")).toBeInTheDocument();
    expect(screen.getByTestId("cast-miss-林野").textContent).toContain("主角");
    expect(screen.getByTestId("cast-miss-银铎")).toBeInTheDocument();
    expect(screen.queryByTestId("cast-miss-阿蓟")).toBeNull(); // 在名单的不提示
  });

  it("加入名单→onPatch chars 追加该名（走 3s 自动保存链，不直接 PUT）", () => {
    const onPatch = vi.fn();
    renderPane({
      form: makeForm({ chars: "阿蓟" }),
      characterNames: ["林野", "阿蓟", "银铎"],
      protagonistName: "林野",
      onPatch,
    });
    fireEvent.click(screen.getByTestId("cast-add-林野"));
    const patch = onPatch.mock.calls.find(([p]) => "chars" in (p as object));
    expect((patch?.[0] as { chars: string }).chars).toBe("阿蓟\n林野");
  });

  it("忽略→该行消失且不 patch（零落库）", () => {
    const onPatch = vi.fn();
    renderPane({
      form: makeForm({ chars: "阿蓟" }),
      characterNames: ["林野", "阿蓟", "银铎"],
      protagonistName: "林野",
      onPatch,
    });
    fireEvent.click(screen.getByTestId("cast-miss-林野").querySelector(".cast-ig")!);
    expect(screen.queryByTestId("cast-miss-林野")).toBeNull();
    expect(onPatch).not.toHaveBeenCalled();
  });

  it("换章→忽略记录不跨章（各自独立）", () => {
    renderPane({
      form: makeForm({ chars: "阿蓟" }),
      characterNames: ["林野", "阿蓟", "银铎"],
      protagonistName: "林野",
      label: "第03章 · 另一章",
    });
    fireEvent.click(screen.getByTestId("cast-miss-林野").querySelector(".cast-ig")!);
    // 忽略后本行消失（域＝第03章）
    expect(screen.queryByTestId("cast-miss-林野")).toBeNull();
  });

  it("在名单的角色→不提示", () => {
    renderPane({
      form: makeForm({ chars: "林野\n阿蓟\n银铎" }),
      characterNames: ["林野", "阿蓟", "银铎"],
      protagonistName: "林野",
    });
    expect(screen.queryByTestId("cast-missing")).toBeNull();
  });

  it("单字名不探测（≥2 字下限：泛称「夜」类章章命中纯噪音）", () => {
    renderPane({
      form: makeForm({ chars: "阿蓟" }),
      characterNames: ["夜", "阿蓟"], // 梗概「夜禁后…」含「夜」，单字卡不提示
      protagonistName: "夜",
    });
    expect(screen.queryByTestId("cast-missing")).toBeNull();
  });

  it("目标字数校验不过时点加入→仍入表单，但弹校验提示（自动保存会静默跳过）", () => {
    renderPane({
      form: makeForm({ chars: "阿蓟", wt: "300" }),
      characterNames: ["林野", "阿蓟", "银铎"],
      protagonistName: "林野",
    });
    fireEvent.click(screen.getByTestId("cast-add-林野"));
    expect(toastState.error).toHaveBeenCalledWith(
      "名单改动暂不落库：本章目标字数需在 500-6000 之间（留空默认 2500）",
    );
  });
});
