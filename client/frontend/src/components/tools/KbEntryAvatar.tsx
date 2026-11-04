// 知识库条目头像（角色设定条目与角色库同源 kb_entries）：有字节出图；
// 无字节（本机从未生成/legacy 无图）出姓氏 SVG 占位——列表恒有头像框。
import { useEffect, useState } from "react";
import { fetchLibraryAvatar } from "@/lib/libraryApi";

export default function KbEntryAvatar({
  entry,
}: {
  entry: { id: string; title: string; has_avatar?: boolean };
}) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    if (!entry.has_avatar) {
      setUrl("");
      return;
    }
    let alive = true;
    fetchLibraryAvatar({
      id: entry.id,
      avatar: {
        has: true,
        url: `/api/character-library/${entry.id}/avatar?variant=full`,
        thumb_url: `/api/character-library/${entry.id}/avatar?variant=thumb`,
      },
    })
      .then((u) => {
        if (alive) setUrl(u);
      })
      .catch(() => {
        if (alive) setUrl("");
      });
    return () => {
      alive = false;
    };
  }, [entry.id, entry.has_avatar]);

  if (url) {
    return (
      <img
        src={url}
        alt=""
        data-testid="kb-entry-avatar-img"
        className="h-9 w-9 flex-none rounded-lg object-cover"
      />
    );
  }
  const ch = (entry.title || "").trim().slice(0, 1) || "角";
  return (
    <svg
      viewBox="0 0 36 36"
      className="h-9 w-9 flex-none rounded-lg"
      aria-hidden="true"
      data-testid="kb-entry-avatar-fallback"
    >
      <rect width="36" height="36" rx="9" style={{ fill: "var(--fg-soft)" }} />
      <text
        x="18"
        y="24"
        textAnchor="middle"
        style={{ fill: "var(--fg)", fontFamily: "var(--font-display)", fontSize: 15 }}
      >
        {ch}
      </text>
    </svg>
  );
}
