import { describe, expect, it } from "vitest";

import { applyStreamEvent } from "./accumulate";
import type { ChatMessage } from "../api/types";

const blank: ChatMessage = { id: "a", role: "assistant", content: "", groups: [] };

describe("applyStreamEvent", () => {
  it("accumulates tokens and a product group", () => {
    let message = blank;
    message = applyStreamEvent(message, { type: "token", delta: "I'd " });
    message = applyStreamEvent(message, { type: "token", delta: "start " });
    message = applyStreamEvent(message, { type: "token", delta: "with Galaxy." });
    message = applyStreamEvent(message, {
      type: "products",
      group: { label: "phone", products: [{ id: 2, title: "Galaxy Budget", description: "", category: "smartphones", price: 199, discountPercentage: 0, rating: 4, stock: 1, availabilityStatus: "In Stock", brand: null, thumbnail: "" }] },
    });
    expect(message.content).toBe("I'd start with Galaxy.");
    expect(message.groups).toHaveLength(1);
    expect(message.groups[0].products[0].title).toBe("Galaxy Budget");
  });
});
