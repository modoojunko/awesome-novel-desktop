import { useEffect, useState } from "react";
import { imageApi, type ImageRef } from "@/lib/imageApi";

/** 签名缩略图：403/过期时只换一次链接，避免无限刷新循环。 */
export default function ImageThumb({
  asset, className, alt = "", full = false,
}: { asset: ImageRef; className?: string; alt?: string; full?: boolean }) {
  const pick = (a: ImageRef) => imageApi.mediaUrl(full ? a.url : a.thumb_url);
  const [src, setSrc] = useState(() => pick(asset));
  const [tried, setTried] = useState(false);
  useEffect(() => {
    setSrc(pick(asset));
    setTried(false);
  }, [asset.asset_id, asset.thumb_url, asset.url, full]);
  return (
    <img
      className={className}
      src={src}
      alt={alt}
      loading="lazy"
      onError={() => {
        if (tried) return;
        setTried(true);
        void imageApi.refreshLinks(asset.asset_id).then((r) => {
          setSrc(imageApi.mediaUrl(full ? r.links.full : r.links.thumb));
        }).catch(() => {});
      }}
    />
  );
}
