/**
 * [uikit 候选] 就地展开的两级级联选择器（2026-09-10 genre-signup-redesign 沉淀，
 * 形态对标 TDesign Cascader 的 `checkStrictly` + `filterable` + `clearable`）。
 *
 * 现网实现：嵌在 `client/frontend/src/components/novel/settings/GenreSettingForm.tsx`
 * 的「01 题材选择器」里（theme 专属、未抽壳）——本文件是通用化候选，首个第二使用者
 * 出现时按采用顺序搬运进 `src/components/ui/`。
 *
 * 与浮层 Cascader 的**唯一本质差异＝就地展开，不用 portal 浮层**：
 * 面板列/侧栏自身是 `overflow-y:auto` 容器，浮层会被裁切并随滚动漂移；
 * 就地展开把面板推进文档流，代价是占位——只适合「表单里的一格」，不适合工具栏。
 *
 * 三条交互裁决（都来自真实用户报障/拍板，换场景也成立）：
 *   1. **浏览 ≠ 选中**：点左列大类只切换右列内容，不改选中值；选中走右列的
 *      显式动作（点子类 / 点「只归到大类」行）。原实现把两者合并，作者只想看看
 *      某大类下有什么，值就被改掉了——离开面板时脏数据被保存，表现为「选过的
 *      题材老是自动变」。
 *   2. **搜索按解读/补充信息命中**，不只按名字：候选多时作者记得的是「大概是
 *      说什么的」，不是确切名词；搜索态拍平成「大类 / 子类」路径行。
 *   3. **每项自带解读**：选中态下方就地展示 desc（子类还带 extra 案例）——
 *      光有标签作者不知道指什么。
 *
 * 键盘：展开自动聚焦搜索框；↑↓ 移动游标（环绕）、Enter 选中当前行、Esc 收起；
 * 渲染与键盘共用同一份 rows memo，避免两套取舍。
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Ico, P } from "@/components/icons";

export interface CascaderItem {
  /** 子类名（存储值即展示名，封闭目录不另造 slug）。 */
  name: string;
  /** 解读：右列副行 + hover title + 搜索命中域。 */
  desc?: string;
  /** 补充信息（如案例）：hover title + 搜索命中域，不占版面。 */
  extra?: string;
}

export interface CascaderGroup {
  /** 大类名（存储值即展示名）。 */
  name: string;
  /** 解读：左列 hover title + 搜索命中域 + 选中态解读区。 */
  desc?: string;
  /** 子类（可空＝只有大类的目录）。 */
  items?: CascaderItem[];
}

export interface CascaderValue {
  group: string;
  /** null＝只选了大类。 */
  item: string | null;
}

/** 一行可选目标：浏览态＝「只归到大类」+ 当前大类子类；搜索态＝全目录命中拍平。 */
interface Row {
  group: string;
  item?: { name: string; desc?: string; extra?: string };
}

export function Cascader({
  groups,
  value,
  onChange,
  onClear,
  placeholder = "请选择",
  searchPlaceholder = "搜索（名 / 说明 / 补充）",
  onlyGroupHint = "只归到大类",
  ariaLabel = "选择器",
}: {
  groups: CascaderGroup[];
  value: CascaderValue | null;
  /** 选了「大类+子类」或「只归大类」（item=null）。值没变时不应回调。 */
  onChange: (v: CascaderValue) => void;
  /** 清空（clearable）；未传则不渲染 ×。 */
  onClear?: () => void;
  placeholder?: string;
  searchPlaceholder?: string;
  /** 右列首行的固定语义（题材场景＝「只归到大类（X）」）。 */
  onlyGroupHint?: string;
  ariaLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [browse, setBrowse] = useState(groups[0]?.name ?? "");
  const [cursor, setCursor] = useState(0);
  const boxRef = useRef<HTMLDivElement | null>(null);
  const searchRef = useRef<HTMLInputElement | null>(null);

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
  }, []);

  const toggle = useCallback(() => {
    setOpen((o) => {
      if (o) {
        setQuery("");
        return false;
      }
      setQuery("");
      setBrowse((cur) => cur || value?.group || groups[0]?.name || "");
      setCursor(0);
      return true;
    });
  }, [value?.group, groups]);

  useEffect(() => {
    if (open) searchRef.current?.focus();
  }, [open]);

  // 点外面 / Esc 收起都挂文档级：点过选项后焦点在按钮上，只挂搜索框会收不起来
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close]);

  const searching = query.trim().length > 0;
  const rows = useMemo<Row[]>(() => {
    if (!searching) {
      const g = groups.find((x) => x.name === browse);
      if (!g) return [];
      return [
        { group: g.name },
        ...(g.items ?? []).map((it) => ({ group: g.name, item: it })),
      ];
    }
    const q = query.trim().toLowerCase();
    const hit = (s?: string) => !!s && s.toLowerCase().includes(q);
    const out: Row[] = [];
    for (const g of groups) {
      if (hit(g.name) || hit(g.desc)) out.push({ group: g.name });
      for (const it of g.items ?? []) {
        if (hit(it.name) || hit(it.desc) || hit(it.extra)) out.push({ group: g.name, item: it });
      }
    }
    return out;
  }, [searching, query, browse, groups]);

  const pick = (r: Row) => {
    onChange({ group: r.group, item: r.item ? r.item.name : null });
    close();
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      e.preventDefault();
      close();
      return;
    }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => {
        const n = rows.length;
        if (n === 0) return 0;
        return e.key === "ArrowDown" ? (c + 1) % n : (c - 1 + n) % n;
      });
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      const r = rows[cursor];
      if (r) pick(r);
    }
  };

  const group = groups.find((x) => x.name === value?.group);
  const item = value?.item ? group?.items?.find((x) => x.name === value.item) : undefined;
  const note = item
    ? { name: item.name, desc: item.desc, extra: item.extra }
    : group
      ? { name: group.name, desc: group.desc, extra: undefined }
      : null;

  return (
    <div className="sel" ref={boxRef} data-od-id="cascader">
      <button
        type="button"
        className={`sel-field${open ? " on" : ""}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        onClick={toggle}
      >
        <span className={value?.group ? "v" : "ph"}>
          {value?.group
            ? value.item
              ? `${value.group} / ${value.item}`
              : value.group
            : placeholder}
        </span>
        {value?.group && onClear && (
          <span
            className="sel-clear"
            role="button"
            aria-label={`清除${ariaLabel}`}
            onClick={(e) => {
              e.stopPropagation();
              onClear();
            }}
          >
            ×
          </span>
        )}
        {/* 展开态靠字段边框变 accent 表达，箭头保持向下（图标集无 chevronUp） */}
        <Ico d={P.chevronDown} className={open ? "open" : undefined} />
      </button>

      {open && (
        <div className="sel-panel">
          <input
            ref={searchRef}
            className="sel-search"
            placeholder={searchPlaceholder}
            value={query}
            spellCheck={false}
            onChange={(e) => {
              setQuery(e.target.value);
              setCursor(0);
            }}
            onKeyDown={onKeyDown}
          />
          {searching ? (
            <ul className="sel-list" role="listbox">
              {rows.map((r, i) => (
                <li key={`${r.group}/${r.item?.name ?? ""}`}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={i === cursor}
                    className={`sel-item${i === cursor ? " cur" : ""}`}
                    onMouseEnter={() => setCursor(i)}
                    onClick={() => pick(r)}
                  >
                    <span className="si-name">
                      {r.item ? (
                        <>
                          <em>{r.group} / </em>
                          {r.item.name}
                        </>
                      ) : (
                        <>
                          {r.group}
                          <em>　{onlyGroupHint}</em>
                        </>
                      )}
                    </span>
                    <span className="si-desc">{r.item ? r.item.desc : groups.find((x) => x.name === r.group)?.desc}</span>
                  </button>
                </li>
              ))}
              {rows.length === 0 && <li className="sel-empty">没有匹配项，换个词试试</li>}
            </ul>
          ) : (
            <div className="sel-cols">
              <ul className="sel-col themes" role="listbox" aria-label={`${ariaLabel}·大类`}>
                {groups.map((g) => (
                  <li key={g.name}>
                    <button
                      type="button"
                      role="option"
                      aria-selected={value?.group === g.name}
                      className={`sel-item${browse === g.name ? " cur" : ""}${
                        value?.group === g.name ? " on" : ""
                      }`}
                      title={g.desc}
                      onClick={() => {
                        setBrowse(g.name); // 浏览 ≠ 选中
                        setCursor(0);
                      }}
                    >
                      <span className="si-name">{g.name}</span>
                    </button>
                  </li>
                ))}
              </ul>
              <ul className="sel-col subs" role="listbox" aria-label={`${ariaLabel}·子类`}>
                {rows.map((r, i) => (
                  <li key={r.item?.name ?? "only"}>
                    <button
                      type="button"
                      role="option"
                      aria-selected={r.item ? value?.item === r.item.name : !value?.item}
                      className={`sel-item${i === cursor ? " cur" : ""}${
                        (r.item ? value?.item === r.item.name : value?.item == null) ? " on" : ""
                      }${r.item ? "" : " only"}`}
                      title={
                        r.item
                          ? `${r.item.desc ?? ""}${r.item.extra ? `　${r.item.extra}` : ""}`
                          : `只标「${r.group}」，不分子类`
                      }
                      onMouseEnter={() => setCursor(i)}
                      onClick={() => pick(r)}
                    >
                      <span className="si-name">
                        {r.item ? r.item.name : `${onlyGroupHint}（${r.group}）`}
                      </span>
                      <span className="si-desc">
                        {r.item ? r.item.desc : "不分小类也行，随时能回来补"}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* 选中即解读：选了子类说子类（更具体），只选大类说大类；都没选不占位 */}
      {note?.desc && (
        <p className="cap-note" data-od-id="cascader-note">
          <b>{note.name}</b>
          {"："}
          {note.desc}
          {note.extra && <span className="eg">{note.extra}</span>}
        </p>
      )}
    </div>
  );
}
