import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { visibleConversations } from "./components/Sidebar";
import { ChatPage } from "./routes/ChatPage";
import { GuidePage } from "./guide/GuidePage";
import type { Conversation } from "./api/types";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo) => {
      const url = String(input);
      if (url.endsWith("/messages")) return json({ messages: [] });
      return json({ conversations: [] });
    }),
  );
});

function conversation(id: string, title: string): Conversation {
  return { id, title, created_at: "", updated_at: "" };
}

function json(body: unknown) {
  return { ok: true, json: async () => body, text: async () => "" };
}

describe("sidebar", () => {
  it("shows one row for a repeated question", () => {
    const conversations = [
      conversation("1", "a phone under 500"),
      conversation("2", "a phone under 500"),
      conversation("3", "New chat"),
      conversation("4", "New chat"),
    ];
    const visible = visibleConversations(conversations);
    expect(visible.map((item) => item.id)).toEqual(["1", "3", "4"]);
  });
});

describe("shell", () => {
  it("renders the empty chat at /", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<ChatPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText("What are you looking for?")).toBeInTheDocument();
    expect(screen.getByText("New chat")).toBeInTheDocument();
  });

  it("renders a deep conversation link", async () => {
    render(
      <MemoryRouter initialEntries={["/c/abc"]}>
        <Routes>
          <Route path="/c/:conversationId" element={<ChatPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText("What are you looking for?")).toBeInTheDocument();
  });

  it("renders the guide diagrams and choice headings", () => {
    render(
      <MemoryRouter>
        <GuidePage />
      </MemoryRouter>,
    );
    expect(screen.getByText("LangChain and typed tools")).toBeInTheDocument();
    expect(screen.getByText("The graph is compiled once")).toBeInTheDocument();
    expect(screen.getByText("Decisions routes, then reviews the cards")).toBeInTheDocument();
    expect(screen.getByTestId("diagram-request")).toBeInTheDocument();
    expect(screen.getByTestId("diagram-turn")).toBeInTheDocument();
    expect(screen.getByTestId("diagram-freshness")).toBeInTheDocument();
  });
});
