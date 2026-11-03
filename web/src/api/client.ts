import { XRequest, type SSEOutput } from "@ant-design/x-sdk";

import type { ChatMessage, Conversation, StreamEvent } from "./types";

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}

export function listConversations(): Promise<{ conversations: Conversation[] }> {
  return fetch("/api/conversations").then((response) => readJson(response));
}

export function createConversation(title?: string): Promise<Conversation> {
  return fetch("/api/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  }).then((response) => readJson(response));
}

export function renameConversation(id: string, title: string): Promise<Conversation> {
  return fetch(`/api/conversations/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  }).then((response) => readJson(response));
}

export function deleteConversation(id: string): Promise<void> {
  return fetch(`/api/conversations/${id}`, { method: "DELETE" }).then((response) => readJson(response));
}

export function loadMessages(id: string): Promise<{ messages: ChatMessage[] }> {
  return fetch(`/api/conversations/${id}/messages`).then((response) => readJson(response));
}

export function abortRun(id: string): Promise<void> {
  return fetch(`/api/conversations/${id}/runs/current`, { method: "DELETE" }).then((response) => readJson(response));
}

function eventFromChunk(chunk: SSEOutput): StreamEvent | null {
  const raw = chunk.data;
  if (!raw) return null;
  return (typeof raw === "string" ? JSON.parse(raw) : raw) as StreamEvent;
}

export function streamTurn(
  id: string,
  text: string,
  onEvent: (event: StreamEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = XRequest<{ text: string }, SSEOutput>(`/api/conversations/${id}/stream`, {
      manual: true,
      headers: { "Content-Type": "application/json" },
      callbacks: {
        onUpdate(chunk) {
          const event = eventFromChunk(chunk);
          if (event) onEvent(event);
        },
        onSuccess() {
          resolve();
        },
        onError(error) {
          reject(error);
        },
      },
    });
    signal.addEventListener("abort", () => request.abort());
    request.run({ text });
  });
}
