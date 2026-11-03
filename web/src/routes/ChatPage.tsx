import { Actions, Bubble, Sender, ThoughtChain } from "@ant-design/x";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { abortRun, createConversation, deleteConversation, listConversations, loadMessages, renameConversation, streamTurn } from "../api/client";
import type { ChatMessage, Conversation, StreamEvent } from "../api/types";
import { ProductCards } from "../components/ProductCards";
import { EmptyState } from "../components/EmptyState";
import { Sidebar } from "../components/Sidebar";
import { shopProvider } from "../provider/shop";

export function ChatPage() {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const sendingRef = useRef(false);

  const refreshList = useCallback(async () => {
    const payload = await listConversations();
    setConversations(payload.conversations);
  }, []);

  useEffect(() => {
    refreshList().catch(() => setConversations([]));
  }, [refreshList]);

  useEffect(() => {
    if (sendingRef.current) return;
    if (!conversationId) {
      setMessages([]);
      return;
    }
    loadMessages(conversationId)
      .then((payload) => {
        if (!sendingRef.current) setMessages(payload.messages);
      })
      .catch(() => setMessages([]));
  }, [conversationId]);

  async function ensureConversation(): Promise<string> {
    if (conversationId) return conversationId;
    const created = await createConversation();
    await refreshList();
    navigate(`/c/${created.id}`);
    return created.id;
  }

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy || sendingRef.current) return;
    sendingRef.current = true;
    const title = trimmed.replace(/\n/g, " ").slice(0, 60);
    if (!conversationId) {
      const existing = conversations.find((item) => item.title === title);
      if (existing) {
        sendingRef.current = false;
        setDraft("");
        navigate(`/c/${existing.id}`);
        return;
      }
    }
    setDraft("");
    setBusy(true);
    setStatus("Looking through the catalog");
    const id = await ensureConversation();
    const userMessage: ChatMessage = { id: `user-${Date.now()}`, role: "user", content: trimmed, groups: [] };
    const assistant: ChatMessage = { id: `assistant-${Date.now()}`, role: "assistant", content: "", groups: [], status: "streaming" };
    setMessages((current) => [...current, userMessage, assistant]);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamTurn(id, trimmed, (event: StreamEvent) => {
        if (event.type === "status" && event.text) setStatus(event.text);
        setMessages((current) => {
          const next = [...current];
          const index = next.findIndex((item) => item.id === assistant.id);
          if (index === -1) return current;
          next[index] = shopProvider.transformMessage({ originMessage: next[index], chunk: event });
          return next;
        });
      }, controller.signal);
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        setMessages((current) => current.map((item) => (item.id === assistant.id ? { ...item, content: item.content || "The reply stopped.", status: "incomplete" } : item)));
      }
    } finally {
      sendingRef.current = false;
      setBusy(false);
      setStatus("");
      abortRef.current = null;
      refreshList().catch(() => undefined);
    }
  }

  async function stop() {
    abortRef.current?.abort();
    if (conversationId) await abortRun(conversationId).catch(() => undefined);
  }

  return (
    <div className="shell">
      <Sidebar
        conversations={conversations}
        activeId={conversationId}
        onSelect={(id) => navigate(`/c/${id}`)}
        onCreate={async () => {
          const created = await createConversation();
          await refreshList();
          navigate(`/c/${created.id}`);
        }}
        onRename={async (id) => {
          const title = window.prompt("Rename chat");
          if (!title) return;
          await renameConversation(id, title);
          await refreshList();
        }}
        onDelete={async (id) => {
          const title = conversations.find((item) => item.id === id)?.title;
          const ids =
            title && title !== "New chat"
              ? conversations.filter((item) => item.title === title).map((item) => item.id)
              : [id];
          await Promise.all(ids.map((item) => deleteConversation(item)));
          await refreshList();
          if (ids.includes(conversationId ?? "")) navigate("/");
        }}
      />
      <section className="thread">
        <header className="topbar">
          <strong>Shopping copilot</strong>
          <Link to="/guide">How it works</Link>
        </header>
        {messages.length === 0 ? <EmptyState onPick={(text) => send(text)} /> : null}
        {status ? <ThoughtChain items={[{ key: "search", title: status, status: "loading" }]} /> : null}
        {messages.length > 0 ? (
          <Bubble.List
            className="transcript"
            autoScroll
            items={messages.map((message) => ({
              key: message.id,
              role: message.role,
              content: message.role === "assistant" ? message : message.content,
            }))}
            role={{
              user: { placement: "end", shape: "round", variant: "filled" },
              assistant: {
                placement: "start",
                shape: "round",
                variant: "outlined",
                contentRender: (content: ChatMessage) => (
                  <div>
                    {content.content ? <p className="assistant-text">{content.content}</p> : null}
                    <ProductCards groups={content.groups} />
                    <Actions
                      items={[
                        { key: "copy", label: "Copy", onItemClick: () => navigator.clipboard?.writeText(content.content) },
                        {
                          key: "reload",
                          label: "Regenerate",
                          onItemClick: () => {
                            const previous = [...messages].reverse().find((item) => item.role === "user");
                            if (previous) send(previous.content);
                          },
                        },
                      ]}
                    />
                  </div>
                ),
              },
            }}
          />
        ) : null}
        <Sender
          value={draft}
          onChange={setDraft}
          loading={busy}
          onSubmit={send}
          onCancel={stop}
          placeholder="Ask for something in the catalog"
        />
      </section>
    </div>
  );
}
