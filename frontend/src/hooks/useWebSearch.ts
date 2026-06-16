import { useState } from "react";

export function useWebSearch() {
  const [enabled, setEnabled] = useState<boolean>(() => {
    return localStorage.getItem("web_search") === "true";
  });

  const toggle = () => {
    setEnabled((prev) => {
      const next = !prev;
      localStorage.setItem("web_search", String(next));
      return next;
    });
  };

  return { enabled, toggle };
}
