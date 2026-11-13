import type {Connection} from "../../../packages/contracts";
import {invoke, isTauri} from "@tauri-apps/api/core";

let connection: Connection;
export async function connect(): Promise<void> {
  if (isTauri()) connection = await invoke<Connection>("service_info");
  else {
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    const token = fragment.get("token") || sessionStorage.getItem("siling-token") || "";
    const url = fragment.get("api") || sessionStorage.getItem("siling-api") || window.location.origin;
    if (!/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(url)) throw new Error("仅允许连接本机语音服务");
    connection = {url, token};
    sessionStorage.setItem("siling-token", token);
    sessionStorage.setItem("siling-api", url);
    if (window.location.hash) history.replaceState(null, "", window.location.pathname);
  }
  if (!connection.token) throw new Error("请通过 SiLing 启动器打开界面，以取得本机会话授权");
}
export async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const response = await fetch(`${connection.url}/api/${path}`, {
    method, headers: {Authorization: `Bearer ${connection.token}`, "Content-Type": "application/json"},
    body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(8000)
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(typeof payload.detail === "string" ? payload.detail : `请求失败 (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export async function exitDesktop(): Promise<void> {
  if (isTauri()) await invoke("exit_app");
}
