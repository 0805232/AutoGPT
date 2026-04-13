"use client";

import { useGetV2ListLibraryAgents } from "@/app/api/__generated__/endpoints/library/library";
import { useSitrepItems } from "@/app/(platform)/library/components/SitrepItem/useSitrepItems";
import type { PulseChipData } from "./PulseChips";
import { useMemo } from "react";

export function usePulseChips(): PulseChipData[] {
  const { data: response } = useGetV2ListLibraryAgents();

  const agents = useMemo(
    () => (response?.status === 200 ? response.data.agents : []),
    [response],
  );

  const sitrepItems = useSitrepItems(agents, 5);

  return useMemo(() => {
    return sitrepItems.map((item) => ({
      id: item.id,
      name: item.agentName,
      status: item.status,
      shortMessage: item.message,
    }));
  }, [sitrepItems]);
}
