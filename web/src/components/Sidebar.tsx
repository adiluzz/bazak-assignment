import { Conversations } from "@ant-design/x";
import { Button } from "antd";

import type { Conversation } from "../api/types";

function groupLabel(iso: string): string {
  const date = new Date(iso);
  const today = new Date();
  const sameDay = date.toDateString() === today.toDateString();
  return sameDay ? "Today" : date.toLocaleDateString();
}

export function visibleConversations(conversations: Conversation[]): Conversation[] {
  const seen = new Set<string>();
  return conversations.filter((item) => {
    if (item.title === "New chat") return true;
    if (seen.has(item.title)) return false;
    seen.add(item.title);
    return true;
  });
}

export function Sidebar({
  conversations,
  activeId,
  onSelect,
  onCreate,
  onRename,
  onDelete,
}: {
  conversations: Conversation[];
  activeId?: string;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onRename: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <aside className="sidebar">
      <Button type="primary" block onClick={onCreate}>
        New chat
      </Button>
      <Conversations
        groupable
        activeKey={activeId}
        onActiveChange={(key) => onSelect(String(key))}
        items={visibleConversations(conversations).map((item) => ({
          key: item.id,
          label: item.title,
          group: groupLabel(item.updated_at),
        }))}
        menu={(item) => ({
          items: [
            { key: "rename", label: "Rename" },
            { key: "delete", label: "Delete", danger: true },
          ],
          onClick: ({ key }) => {
            if (key === "rename") onRename(String(item.key));
            if (key === "delete") onDelete(String(item.key));
          },
        })}
      />
    </aside>
  );
}
