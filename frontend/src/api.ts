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
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

const OWNER_KEY = "profile_agent_owner_secret";

export function getOwnerSecret(): string {
  return sessionStorage.getItem(OWNER_KEY) || "";
}

export function setOwnerSecret(value: string) {
  sessionStorage.setItem(OWNER_KEY, value);
}

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    return data.detail || res.statusText;
  } catch {
    return res.statusText;
  }
}

export async function fetchPublicConfig(): Promise<PublicConfig> {
  const res = await fetch("/api/config/public");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
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
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent_id: agentId, message, history }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
