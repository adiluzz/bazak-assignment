import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import React from "react";
import { afterEach, vi } from "vitest";

afterEach(() => cleanup());

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

class IntersectionObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return [];
  }
}

globalThis.ResizeObserver = ResizeObserverStub as typeof ResizeObserver;
globalThis.IntersectionObserver = IntersectionObserverStub as typeof IntersectionObserver;
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent() {
      return false;
    },
  }),
});

vi.mock("@ant-design/x", async () => {
  const actual = await vi.importActual<typeof import("@ant-design/x")>("@ant-design/x");
  return {
    ...actual,
    Mermaid: ({ children }: { children: string }) => React.createElement("pre", { className: "diagram-source" }, children),
  };
});
