import { useVan } from "../state";
import { AdminPanel } from "../components/AdminPanel";
import { EventLog } from "../components/EventLog";

export function SettingsTab() {
  const { log } = useVan();
  return (
    <div className="tab-grid stack">
      <AdminPanel />
      <section className="panel">
        <EventLog log={log} />
      </section>
    </div>
  );
}
