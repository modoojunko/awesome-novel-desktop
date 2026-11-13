"""AI 生成内容显式标识单源（人工智能生成合成内容标识办法 2025-09-01 施行）。

提供下载/复制/导出功能的文件须带显式标识（办法第四条）；拆书出口的作家 md
已在 deconstruct/mdrender.py 自带声明（含原书版权口径），本模块供其余导出
面（成稿下载 / 作品包 / 章节归档）统一取用。

文案口径：**不带**「原书版权归原作者」——那些是拆书产物专属；成稿/作品是
作家自己的书，标识只声明 AI 辅助生成事实。重复追加由 with_ai_notice 幂等。
"""

from __future__ import annotations

AI_NOTICE = "本文件由 AI 辅助生成，仅供个人学习与创作参考。"


def with_ai_notice(text: str, *, notice: str = AI_NOTICE) -> str:
    """给文本导出追加显式标识（已含则不重复；容忍空白差异的朴素包含判断）。"""
    if notice in text:
        return text
    return text.rstrip() + "\n\n" + notice + "\n"
