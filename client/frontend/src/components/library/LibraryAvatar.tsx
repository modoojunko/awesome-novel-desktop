// 库卡头像（c-character-library）：字节走鉴权 fetch（<img> 不带 Bearer），按卡缓存 objectURL。
// 无图/加载失败一律回落到姓字块（与书内角色页同款兜底）。
import { useEffect, useState } from "react";
import { fetchLibraryAvatar, type LibraryCard } from "@/lib/libraryApi";

export default function LibraryAvatar({
  card,
  size = "md",
  className = "",
}: {
  card: Pick<LibraryCard, "id" | "name" | "avatar">;
  size?: "md" | "sm" | "lg";
  className?: string;
}) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    if (!card.avatar?.has) {
      setUrl("");
      return;
    }
    let alive = true;
    fetchLibraryAvatar(card, "thumb")
      .then((u) => {
        if (alive) setUrl(u);
      })
      .catch(() => {
        if (alive) setUrl("");
      });
    return () => {
      alive = false;
    };
  }, [card.id, card.avatar?.has]);

  const sizeCls = size === "md" ? "" : ` ${size}`;
  return (
    <span className={`lib-ava${sizeCls}${className ? " " + className : ""}`} aria-hidden="true">
      {url ? <img src={url} alt="" /> : (card.name || "角").slice(0, 1)}
    </span>
  );
}
