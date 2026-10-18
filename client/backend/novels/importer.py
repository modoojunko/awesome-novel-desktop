"""Novel importer — parse markdown/docx files into structured volume/chapter data.

Three public functions:
  - parse_markdown(content, filename)  — markdown/txt text parser
  - parse_docx(filepath)               — docx parser (requires python-docx)
  - parse_file(filepath, filename)     — dispatcher by extension
"""

import os
import re
from dataclasses import dataclass, field

# ── Data types ─────────────────────────────────────────────────────────────────


@dataclass
class ChapterData:
    title: str
    content: str          # body text, title line excluded
    word_count: int


@dataclass
class VolumeData:
    title: str
    chapters: list[ChapterData] = field(default_factory=list)


@dataclass
class ParseWarning:
    type: str             # 'orphan_text' | 'no_volume_title' | 'no_chapter_title'
    message: str
    details: dict | None


@dataclass
class ParseResult:
    volumes: list[VolumeData] = field(default_factory=list)
    warnings: list[ParseWarning] = field(default_factory=list)
    title: str = ""


# 导入模板：与下方解析约定一致（# 卷 / ## 章）
IMPORT_TEMPLATE_MD = """# 卷一　起点

## 第一章　初来乍到

这里是正文。从第二章起，每一章都用自己的二级标题开头。

## 第二章　新的名字

正文内容。

# 卷二　波澜

## 第一章　风起

正文内容。

## 第二章　暗涌

正文内容。
"""


# ── Helpers ────────────────────────────────────────────────────────────────────


def parse_txt_manifest(raw: bytes, filename: str = "") -> dict:
    """A 路 txt 入口：统一复用 deconstruct.textparse，输出冻结 manifest。

    旧 markdown/docx 函数保留给历史兼容；新书架导入只走本函数。
    """
    from deconstruct.textparse import build_manifest

    return build_manifest(raw, filename)


def _count_chars(text: str) -> int:
    """Count visible characters (Chinese-friendly word count)."""
    return len(text.replace(" ", "").replace("\n", "").replace("\r", ""))


def _volume_header(line: str) -> str | None:
    """If line is a level-1 heading (# title), return the title, else None."""
    m = re.match(r"^#\s+(.+)$", line)
    return m.group(1).strip() if m else None


def _chapter_header(line: str) -> str | None:
    """If line is a level-2 heading (## title), return the title, else None."""
    m = re.match(r"^##\s+(.+)$", line)
    return m.group(1).strip() if m else None


# ── Markdown parser ────────────────────────────────────────────────────────────


def parse_markdown(content: str, filename: str = "") -> ParseResult:
    """Parse markdown text into structured volume/chapter data.

    State machine with 3 states:
      SCANNING   — before any header
      IN_VOLUME  — after a # heading (volume)
      IN_CHAPTER — after a ## heading (chapter)

    Auto-creation fallbacks:
      - No # but ## exists           → default volume "正文"
      - No ## but # exists           → default chapter "第1章"
      - Neither # nor ##             → empty volumes with warning
    """
    lines = content.split("\n")
    volumes: list[VolumeData] = []
    warnings: list[ParseWarning] = []
    orphan_lines: list[str] = []

    SCANNING, IN_VOLUME, IN_CHAPTER = 0, 1, 2
    state = SCANNING
    cur_vol: VolumeData | None = None
    cur_ch: ChapterData | None = None
    auto_volume_title = "正文"
    next_auto_chapter = 1
    first_heading_title = ""  # Track first # for overall work title

    def _close_chapter():
        nonlocal cur_ch
        if cur_ch is not None:
            cur_ch.word_count = _count_chars(cur_ch.content)
            if cur_vol is not None:
                cur_vol.chapters.append(cur_ch)
            cur_ch = None

    def _close_volume():
        nonlocal cur_vol
        _close_chapter()
        if cur_vol is not None:
            volumes.append(cur_vol)
            cur_vol = None

    def _ensure_volume():
        """Create default volume if none exists."""
        nonlocal cur_vol, state
        if cur_vol is None:
            cur_vol = VolumeData(title=auto_volume_title)
            state = IN_VOLUME

    for raw in lines:
        line = raw.rstrip("\r")
        vt = _volume_header(line)
        ct = _chapter_header(line)

        if vt is not None:
            # ── Volume header (#) ──────────────────────────────────
            _close_volume()
            if not first_heading_title:
                first_heading_title = vt  # First # heading = work title
            cur_vol = VolumeData(title=vt)
            state = IN_VOLUME
            next_auto_chapter = 1

        elif ct is not None:
            # ── Chapter header (##) ─────────────────────────────────
            _close_chapter()
            _ensure_volume()
            cur_ch = ChapterData(title=ct, content="", word_count=0)
            state = IN_CHAPTER

        elif line.strip() == "":
            # Empty line — preserve spacing in current chapter
            if cur_ch is not None:
                cur_ch.content += "\n"
            continue

        else:
            # ── Body text ──────────────────────────────────────────
            if state == SCANNING:
                orphan_lines.append(line)

            elif state == IN_VOLUME:
                # Text inside a volume but before any chapter heading
                # Auto-create a default chapter
                title = f"第{next_auto_chapter}章"
                next_auto_chapter += 1
                cur_ch = ChapterData(title=title, content=line + "\n", word_count=0)
                state = IN_CHAPTER

            elif state == IN_CHAPTER and cur_ch is not None:
                cur_ch.content += line + "\n"

    # ── Flush remaining ──────────────────────────────────────────────────────
    _close_volume()

    # ── Handle orphan text ──────────────────────────────────────────────────
    if orphan_lines:
        orphan_content = "\n".join(orphan_lines)
        preview = orphan_lines[0][:30]
        # Append orphan text to the last chapter of the first volume, if any
        if volumes and volumes[0].chapters:
            first_ch = volumes[0].chapters[-1]
            first_ch.content = orphan_content + "\n" + first_ch.content
            first_ch.word_count = _count_chars(first_ch.content)

        warnings.append(ParseWarning(
            type="orphan_text",
            message=f"发现 {len(orphan_lines)} 行游离文字: \"{preview}...\"",
            details={"preview": preview},
        ))

    # ── Determine title ─────────────────────────────────────────────────────
    # Priority: first # heading > filename > fallback
    title = first_heading_title
    if not title:
        title = os.path.splitext(filename)[0] if filename else ""
    if not title:
        title = "未命名作品"

    # ── Structure warnings ──────────────────────────────────────────────────
    if not volumes:
        warnings.append(ParseWarning(
            type="no_volume_title",
            message="未找到 Markdown 标题结构（# 或 ##）",
            details=None,
        ))

    return ParseResult(volumes=volumes, warnings=warnings, title=title)


# ── DOCX parser ────────────────────────────────────────────────────────────────


def parse_docx(filepath: str) -> ParseResult:
    """Parse a .docx file into structured volume/chapter data.

    Heading 1 style → volume title (like # in markdown)
    Heading 2 style → chapter title (like ## in markdown)
    Normal paragraphs → chapter body text
    """
    try:
        from docx import Document
    except ImportError:
        raise ImportError(
            "python-docx is required to parse .docx files. "
            "Install with: pip install python-docx"
        )

    doc = Document(filepath)
    volumes: list[VolumeData] = []
    warnings: list[ParseWarning] = []

    cur_vol: VolumeData | None = None
    cur_ch: ChapterData | None = None
    orphan_lines: list[str] = []
    next_auto_chapter = 1
    first_heading_title = ""

    def _close_chapter():
        nonlocal cur_ch
        if cur_ch is not None:
            cur_ch.word_count = _count_chars(cur_ch.content)
            if cur_vol is not None:
                cur_vol.chapters.append(cur_ch)
            cur_ch = None

    def _close_volume():
        nonlocal cur_vol
        _close_chapter()
        if cur_vol is not None:
            volumes.append(cur_vol)
            cur_vol = None

    for para in doc.paragraphs:
        text = para.text.strip()
        style = para.style.name if para.style else ""

        if not text:
            if cur_ch is not None:
                cur_ch.content += "\n"
            continue

        is_h1 = style.startswith(("Heading 1", "heading 1"))
        is_h2 = style.startswith(("Heading 2", "heading 2"))

        if is_h1:
            # Volume heading
            _close_volume()
            if not first_heading_title:
                first_heading_title = text
            cur_vol = VolumeData(title=text)
            next_auto_chapter = 1

        elif is_h2:
            # Chapter heading
            _close_chapter()
            if cur_vol is None:
                cur_vol = VolumeData(title="正文")
            cur_ch = ChapterData(title=text, content="", word_count=0)
            next_auto_chapter += 1

        else:
            # Body paragraph
            if cur_ch is not None:
                cur_ch.content += text + "\n"
            elif cur_vol is not None:
                # In volume but no chapter yet — auto-create
                title = f"第{next_auto_chapter}章"
                next_auto_chapter += 1
                cur_ch = ChapterData(title=title, content=text + "\n", word_count=0)
            else:
                # Outside any structure — orphan text
                orphan_lines.append(text)

    # ── Flush ────────────────────────────────────────────────────────────────
    _close_volume()

    # ── Handle orphan text ──────────────────────────────────────────────────
    if orphan_lines:
        orphan_content = "\n".join(orphan_lines)
        preview = orphan_lines[0][:30]
        if volumes and volumes[0].chapters:
            first_ch = volumes[0].chapters[-1]
            first_ch.content = orphan_content + "\n" + first_ch.content
            first_ch.word_count = _count_chars(first_ch.content)

        warnings.append(ParseWarning(
            type="orphan_text",
            message=f"发现 {len(orphan_lines)} 行游离文字: \"{preview}...\"",
            details={"preview": preview},
        ))

    # ── Determine title ─────────────────────────────────────────────────────
    title = first_heading_title
    if not title:
        title = os.path.splitext(os.path.basename(filepath))[0]
    if not title:
        title = "未命名作品"

    if not volumes:
        warnings.append(ParseWarning(
            type="no_volume_title",
            message="未找到文档标题结构（Heading 1 或 Heading 2）",
            details=None,
        ))

    return ParseResult(volumes=volumes, warnings=warnings, title=title)


# ── File dispatcher ────────────────────────────────────────────────────────────


def parse_file(filepath: str, filename: str) -> ParseResult:
    """Parse a file by its extension.

    Supported: .md, .txt, .docx
    Raises ValueError for unsupported extensions.
    """
    _, ext = os.path.splitext(filename)
    ext = ext.lower()

    # Fall back to filepath extension when filename yields none
    if not ext:
        _, ext = os.path.splitext(filepath)
        ext = ext.lower()

    if ext in (".md", ".txt"):
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
        return parse_markdown(content, filename)

    if ext == ".docx":
        return parse_docx(filepath)

    raise ValueError(
        f"不支持的文件格式，仅支持 .md、.txt、.docx (got: {ext})"
    )
