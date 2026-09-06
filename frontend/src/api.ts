export type AgentMeta = {
  id: string;
  display_name: string;
  headline: string;
  linkedin_url: string;
  github_username: string;
  scholar_url: string;
  created_at: string;
  updated_at: string;
  source_count: number;
  chunk_count: number;
};

export type PublicConfig = {
  public_chat_only: boolean;
  owner_auth_required: boolean;
  max_chat_history: number;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

const OWNER_KEY = "profile_agent_owner_secret";
/** Used only if `/api/config/public` has not loaded yet or failed. */
const FALLBACK_MAX_CHAT_HISTORY = 40;

let maxChatHistory = FALLBACK_MAX_CHAT_HISTORY;
let publicConfigPromise: Promise<PublicConfig> | null = null;

export function getOwnerSecret(): string {
  return sessionStorage.getItem(OWNER_KEY) || "";
}

export function setOwnerSecret(value: string) {
  sessionStorage.setItem(OWNER_KEY, value);
}

function formatDetail(detail: unknown): string {
  if (detail == null || detail === "") return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) {
          const loc = Array.isArray((item as { loc?: unknown }).loc)
            ? (item as { loc: unknown[] }).loc.filter((part) => part !== "body").join(".")
            : "";
          const msg = String((item as { msg: unknown }).msg);
          return loc ? `${loc}: ${msg}` : msg;
        }
        try {
          return JSON.stringify(item);
        } catch {
          return String(item);
        }
      })
      .filter(Boolean)
      .join("; ");
  }
  try {
    return JSON.stringify(detail);
  } catch {
    return String(detail);
  }
}

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    return formatDetail(data.detail) || res.statusText;
  } catch {
    return res.statusText;
  }
}

export async function fetchPublicConfig(): Promise<PublicConfig> {
  if (!publicConfigPromise) {
    publicConfigPromise = (async () => {
      const res = await fetch("/api/config/public");
      if (!res.ok) throw new Error(await parseError(res));
      const data: PublicConfig = await res.json();
      if (typeof data.max_chat_history === "number" && data.max_chat_history > 0) {
        maxChatHistory = data.max_chat_history;
      }
      return data;
    })().catch((err) => {
      publicConfigPromise = null;
      throw err;
    });
  }
  return publicConfigPromise;
}

export async function fetchAgent(id: string): Promise<AgentMeta> {
  const res = await fetch(`/api/agents/${id}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function createAgent(form: FormData): Promise<AgentMeta> {
  const headers: HeadersInit = {};
  const secret = getOwnerSecret();
  if (secret) headers["X-Owner-Secret"] = secret;
  const res = await fetch("/api/agents", { method: "POST", body: form, headers });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function sendChat(
  agentId: string,
  message: string,
  history: ChatMessage[],
): Promise<{ answer: string }> {
  await fetchPublicConfig().catch(() => undefined);
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      agent_id: agentId,
      message,
      history: history.slice(-maxChatHistory),
    }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
