import { useVan } from "../state";
import { Chat } from "../components/Chat";

export function AssistantTab() {
  const { notices, assistant } = useVan();
  return (
    <div className="tab-grid stack">
      <Chat notices={notices} assistant={assistant} />
    </div>
  );
}
