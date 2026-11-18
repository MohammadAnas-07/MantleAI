import { useEffect, useState } from "react";

// Returns `value` only after it has stopped changing for `delayMs` milliseconds.
// Used by the search box so typing doesn't send a request per key press.
export function useDebounce<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}
