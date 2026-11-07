import type { DynamicSnapshot, Snapshot } from "./types";

const token = window.location.hash.startsWith("#") ? window.location.hash.slice(1) : "";

export class BridgeError extends Error {}

export async function invoke<T>(action: string, payload: Record<string, unknown> = {}): Promise<T> {
  const response = await fetch("/api", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Authenticator-MUI": token,
    },
    body: JSON.stringify({ action, payload }),
    cache: "no-store",
    credentials: "omit",
  });
  const body = (await response.json()) as { ok: boolean; result?: T; error?: string };
  if (!response.ok || !body.ok) {
    throw new BridgeError(body.error || "本地界面服务不可用");
  }
  return body.result as T;
}

/**
 * Use the terminal-only loopback transport for SSH bytes. It is authenticated
 * with the same per-run bridge token, but bypasses Tk because no vault or UI
 * state is accessed for terminal input, output, resize, or close operations.
 */
export async function terminalInvoke<T>(
  action: string,
  payload: Record<string, unknown> = {},
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch("/api", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Authenticator-MUI": token,
    },
    body: JSON.stringify({ action, payload }),
    cache: "no-store",
    credentials: "omit",
    signal,
  });
  const body = (await response.json()) as { ok: boolean; result?: T; error?: string };
  if (!response.ok || !body.ok) {
    throw new BridgeError(body.error || "本地终端服务不可用");
  }
  return body.result as T;
}

export function snapshot(payload: Record<string, unknown>): Promise<Snapshot> {
  return invoke<Snapshot>("snapshot", payload);
}

export function dynamicSnapshot(payload: Record<string, unknown>): Promise<DynamicSnapshot> {
  return invoke<DynamicSnapshot>("dynamic", payload);
}
