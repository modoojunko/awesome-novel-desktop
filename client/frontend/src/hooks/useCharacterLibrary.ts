// 角色库列表 hook（c-character-library）：普通 useQuery（无轮询）；写操作后失效同源 key。
import { useQuery } from "@tanstack/react-query";
import { listLibrary, type LibraryListData } from "@/lib/libraryApi";
import { queryKeys } from "@/lib/queryKeys";

export function useCharacterLibrary(enabled = true) {
  const { data, isLoading, error, refetch } = useQuery<LibraryListData>({
    queryKey: queryKeys.characterLibrary,
    queryFn: listLibrary,
    enabled,
    staleTime: 10_000,
  });
  return { data, isLoading, error: error ? (error instanceof Error ? error.message : "加载失败") : "", refetch };
}
