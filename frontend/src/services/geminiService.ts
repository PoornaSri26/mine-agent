import { apiJson } from './api';

export interface AgentEvent {
  id: string;
  agent: string;
  name: string;
  role: string;
  status: 'done' | 'warn' | 'error';
  ms: number;
  summary: string;
  bullets?: string[];
}

export interface ChatSessionSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface StoredMessage {
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  trace?: AgentEvent[] | null;
}

export interface ChatSession {
  id: string;
  title: string;
  updated_at: string;
  messages: StoredMessage[];
}

export interface ChatResponse {
  response: string;
  session_id: string;
  confidence: number;
  intent: string;
  trace: AgentEvent[];
  hazard?: { id: string; label: string; severity: string; confidence: number };
  plan?: { rewritten?: string; rounds?: number };
}

export interface AgentInfo {
  id: string;
  name: string;
  role: string;
  stage: number;
  description: string;
  tools: string[];
}

export interface AgentsResponse {
  agents: AgentInfo[];
  pipeline: string[];
  llm: { enabled: boolean; model: string; mode: string };
}

export const getChatResponse = (message: string, sessionId: string | null) =>
  apiJson<ChatResponse>('/query', {
    method: 'POST',
    body: JSON.stringify({ query: message, session_id: sessionId }),
  });

export const listChatSessions = async () => {
  const data = await apiJson<{ sessions: ChatSessionSummary[] }>('/sessions');
  return data.sessions;
};

export const createChatSession = () =>
  apiJson<{ session_id: string; title: string }>('/sessions', {
    method: 'POST',
    body: JSON.stringify({ title: 'New chat' }),
  });

export const loadChatSession = (sessionId: string) =>
  apiJson<ChatSession>(`/sessions/${encodeURIComponent(sessionId)}`);

export const renameChatSession = (sessionId: string, title: string) =>
  apiJson<{ ok: boolean }>(`/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
  });

export const deleteChatSession = (sessionId: string) =>
  apiJson<{ ok: boolean }>(`/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  });

export const getAgents = () => apiJson<AgentsResponse>('/agents');
