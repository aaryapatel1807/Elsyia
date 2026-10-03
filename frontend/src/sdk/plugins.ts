/** Typed client for Elsyia's local plugin boundary.
 *
 * The SDK is transport-only: the backend remains the authority for trust,
 * permissions, lifecycle, confirmation, and audit decisions.
 */

import { apiBase } from "../lib/api";

export type PluginState = "discovered" | "enabled" | "disabled" | "blocked" | "failed" | string;

export interface PluginInfo {
  id: string;
  name: string;
  version: string;
  description: string;
  state: PluginState;
  tools: string[];
  loaded_tools: string[];
  permissions: string[];
  requires_confirmation: boolean;
  trusted: boolean;
  enabled_by_default: boolean;
  publisher: string | null;
  signature_algorithm: string | null;
  signature_status: "unsigned_local" | "verified" | "invalid" | string;
  signing_key_fingerprint: string | null;
  error: string | null;
}

export interface PluginCatalogResponse {
  plugins: PluginInfo[];
}

export interface PluginActionResponse {
  status: string;
  plugin_id?: string;
  plugin?: PluginInfo;
  confirmation_required?: boolean;
  confirmation_message?: string | null;
  error?: string | null;
  [key: string]: unknown;
}

export interface PluginExecutionResponse extends PluginActionResponse {
  tool_name?: string;
  result?: unknown;
  metadata?: Record<string, unknown> | null;
}

export interface PluginClientOptions {
  /** Defaults to the local backend API and may be overridden for tests. */
  baseUrl?: string;
  fetcher?: typeof fetch;
}

export class PluginClient {
  private readonly baseUrl: string;
  private readonly fetcher: typeof fetch;

  constructor(options: PluginClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? apiBase()).replace(/\/$/, "");
    this.fetcher = options.fetcher ?? fetch;
  }

  async list(signal?: AbortSignal): Promise<PluginCatalogResponse> {
    return this.request<PluginCatalogResponse>("/plugins", { signal });
  }

  async refresh(signal?: AbortSignal): Promise<PluginActionResponse> {
    return this.request<PluginActionResponse>("/plugins/refresh", { method: "POST", signal });
  }

  async enable(pluginId: string, confirmed = false, signal?: AbortSignal): Promise<PluginActionResponse> {
    return this.request<PluginActionResponse>(`/plugins/${encodeURIComponent(pluginId)}/enable`, {
      method: "POST",
      signal,
      body: JSON.stringify({ confirmed }),
    });
  }

  async disable(pluginId: string, signal?: AbortSignal): Promise<PluginActionResponse> {
    return this.request<PluginActionResponse>(`/plugins/${encodeURIComponent(pluginId)}/disable`, {
      method: "POST",
      signal,
    });
  }

  async execute(
    pluginId: string,
    tool: string,
    arguments_: Record<string, unknown> = {},
    confirmed = false,
    signal?: AbortSignal,
  ): Promise<PluginExecutionResponse> {
    return this.request<PluginExecutionResponse>(`/plugins/${encodeURIComponent(pluginId)}/execute`, {
      method: "POST",
      signal,
      body: JSON.stringify({ tool, arguments: arguments_, confirmed }),
    });
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await this.fetcher(`${this.baseUrl}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
    });
    const payload = (await response.json()) as T & { detail?: string };
    if (!response.ok) throw new Error(payload.detail ?? `Plugin request failed: ${response.status}`);
    return payload;
  }
}

export const pluginClient = new PluginClient();
