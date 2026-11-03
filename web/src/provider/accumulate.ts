import type { ChatMessage, StreamEvent } from "../api/types";

export function applyStreamEvent(message: ChatMessage, event: StreamEvent): ChatMessage {
  if (event.type === "token") {
    return { ...message, content: message.content + (event.delta ?? "") };
  }
  if (event.type === "products" && event.group) {
    return { ...message, groups: [...message.groups, event.group] };
  }
  if (event.type === "done") {
    return { ...message, id: event.message_id || message.id, status: "complete" };
  }
  if (event.type === "error") {
    return { ...message, content: message.content || event.text || "Something went wrong.", status: "incomplete" };
  }
  return message;
}
