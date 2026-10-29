// 书内卡「收入角色库／同步到角色库」（c-character-library）：
// 已收录态由库列表同源 key 判定；收录幂等由后端兜底。
// 用应用级 queryClient 单例取数（非 hook）——面板测试/挂载不依赖 QueryClientProvider。
import { useEffect, useState } from "react";
import { toast } from "@/lib/toast";
import { importCardFromBook, listLibrary, syncCardFromBook, type LibraryCard } from "@/lib/libraryApi";
import { queryKeys } from "@/lib/queryKeys";
import { queryClient } from "@/lib/queryClient";

export default function CollectToLibrary({
  novelId,
  characterId,
  characterName,
}: {
  novelId: string;
  characterId: string;
  characterName: string;
}) {
  const [busy, setBusy] = useState(false);
  const [mine, setMine] = useState<LibraryCard | null>(null);

  const refresh = async () => {
    try {
      const data = await queryClient.fetchQuery({
        queryKey: queryKeys.characterLibrary,
        queryFn: listLibrary,
        staleTime: 10_000,
      });
      setMine(
        data.items.find(
          (c) => c.src.kind === "book" && c.src.ref === novelId && c.src.character_id === characterId,
        ) || null,
      );
    } catch {
      // 取不到库列表时按「未收录」呈现（初始即 null）；点按幂等由后端兜底
    }
  };

  useEffect(() => {
    void refresh();
    // 只随卡身份变化重查（库侧变更由本组件操作后自刷新）
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [novelId, characterId]);

  const onClick = async () => {
    setBusy(true);
    try {
      if (mine) {
        await syncCardFromBook(mine.id);
        toast.success(`已把「${characterName}」的书内最新设定同步进库卡`);
      } else {
        const result = await importCardFromBook(novelId, characterId, false);
        toast.success(
          result.created ? `已把「${characterName}」收进角色库` : `「${characterName}」已经在角色库里了`,
        );
      }
      await queryClient.invalidateQueries({ queryKey: queryKeys.characterLibrary });
      await refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "操作失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <button type="button" onClick={() => void onClick()} disabled={busy} data-testid="char-collect">
      {mine ? "同步到角色库" : "收入角色库"}
    </button>
  );
}
