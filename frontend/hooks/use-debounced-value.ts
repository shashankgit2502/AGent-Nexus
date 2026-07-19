"use client";

import { useEffect, useState } from "react";

/**
 * Debounce a fast-changing value (e.g. a search box) so dependent work — here the
 * model-search query (ITEM 1) — fires only after the user pauses. Returns the
 * latest value once `delay` ms have elapsed without a further change.
 */
export function useDebouncedValue<T>(value: T, delay = 250): T {
  const [debounced, setDebounced] = useState<T>(value);

  useEffect(() => {
    const handle = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(handle);
  }, [value, delay]);

  return debounced;
}
