import { useCallback, useEffect, useRef, useState } from "react";
import { invoke } from "./bridge";
import type { ModuleName } from "./types";

/** Share the selected module across the two retained desktop renderers. */
export function useWorkspaceModule(active: boolean, compact = false) {
  const [module, setModule] = useState<ModuleName>("otp");
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const generation = useRef(0);

  useEffect(() => {
    const request = ++generation.current;
    setReady(false);
    if (!active) return;
    void invoke<{ module: ModuleName }>("active_module").then((result) => {
      if (generation.current !== request) return;
      setModule(compact && result.module === "servers" ? "otp" : result.module);
      setReady(true);
      setError("");
    }).catch((caught) => {
      if (generation.current === request) setError(caught instanceof Error ? caught.message : "无法读取当前模块");
    });
    return () => { ++generation.current; };
  }, [active, compact]);

  const select = useCallback(async (next: ModuleName) => {
    if (compact && next === "servers") return false;
    const request = ++generation.current;
    try {
      const result = await invoke<{ module: ModuleName }>("set_module", { module: next });
      if (generation.current !== request) return false;
      setModule(result.module);
      setReady(true);
      setError("");
      return true;
    } catch (caught) {
      if (generation.current === request) setError(caught instanceof Error ? caught.message : "无法切换模块");
      return false;
    }
  }, [compact]);

  return { module, ready: active && ready, select, error };
}
