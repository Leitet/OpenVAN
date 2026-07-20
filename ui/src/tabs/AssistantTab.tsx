import { useVan } from "../state";
import { Chat } from "../components/Chat";
import { LearnedMemory } from "../components/LearnedMemory";

export function AssistantTab() {
  const { notices, assistant } = useVan();
  return (
    <div className="assistant-tab">
      <Chat notices={notices} assistant={assistant} />
      <LearnedMemory />
    </div>
  );
}
