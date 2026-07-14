"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";
import {
  parseViewState,
  serializeViewState,
  type WorkspaceViewState,
} from "./view-state";

export function useWorkspaceState() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const state = useMemo(
    () => parseViewState(new URLSearchParams(searchParams)),
    [searchParams],
  );

  const update = useCallback(
    (patch: Partial<WorkspaceViewState>, committed = false) => {
      const next = { ...state, ...patch };
      const query = serializeViewState(next).toString();
      const href = query ? `${pathname}?${query}` : pathname;
      if (committed) router.push(href, { scroll: false });
      else router.replace(href, { scroll: false });
    },
    [pathname, router, state],
  );

  return { state, update };
}
