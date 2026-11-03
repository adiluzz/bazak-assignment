import { Prompts, Welcome } from "@ant-design/x";

const PROMPTS = [
  { key: "phone", label: "A phone under 500", description: "A priced search" },
  { key: "cheap", label: "Something cheap and cool", description: "A vague wish" },
  { key: "flight", label: "A flight to Tokyo", description: "Outside the catalog" },
  { key: "both", label: "A laptop and a watch", description: "Two requests at once" },
];

export function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="empty-state">
      <Welcome
        title="What are you looking for?"
        description="I can look through beauty, phones, laptops, watches, groceries, and the rest of the local catalog. I can't book a flight."
      />
      <Prompts
        title="Try one"
        items={PROMPTS}
        wrap
        onItemClick={(info) => onPick(String(info.data.label ?? ""))}
      />
    </div>
  );
}
