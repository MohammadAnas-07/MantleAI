import { useSyncExternalStore } from "react";

export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      if (typeof window.matchMedia !== "function") return () => undefined;
      const list = window.matchMedia(query);
      list.addEventListener("change", onChange);
      return () => {
        list.removeEventListener("change", onChange);
      };
    },
    () => typeof window.matchMedia === "function" && window.matchMedia(query).matches,
  );
}

export const useIsNarrow = () => useMediaQuery("(max-width: 767px)");
/** Under 1024px the shell starts with the AI panel collapsed so the main column keeps room. */
export const useIsMedium = () => useMediaQuery("(max-width: 1023px)");
