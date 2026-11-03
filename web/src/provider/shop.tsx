import { AbstractChatProvider, XRequest } from "@ant-design/x-sdk";

import type { ChatMessage, StreamEvent } from "../api/types";
import { applyStreamEvent } from "./accumulate";

type Input = { text: string };

export class ShopProvider extends AbstractChatProvider<ChatMessage, Input, StreamEvent> {
  constructor() {
    super({
      request: XRequest<Input, StreamEvent>("/api/conversations", { manual: true }),
    });
  }

  transformParams(params: Partial<Input>): Input {
    return { text: params.text ?? "" };
  }

  transformLocalMessage(params: Partial<Input>): ChatMessage {
    return { id: "local", role: "user", content: params.text ?? "", groups: [] };
  }

  transformMessage(info: { originMessage?: ChatMessage; chunk: StreamEvent }): ChatMessage {
    const base = info.originMessage ?? { id: "assistant", role: "assistant" as const, content: "", groups: [] };
    return applyStreamEvent(base, info.chunk);
  }
}

export const shopProvider = new ShopProvider();
