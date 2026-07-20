import { PlugZap } from "lucide-react";
import { useT } from "../i18n";
import { navigateTo } from "../navigation";

// Shown where a domain has no provider ("everything is an integration"): the
// values honestly read "—", and this points at the fix — install a source.
export function NoSource() {
  const t = useT();
  return (
    <div className="no-source">
      <PlugZap size={14} />
      <span>{t("noSource.hint")}</span>
      <button className="mini" onClick={() => navigateTo("settings", "integrations")}>
        {t("noSource.action")}
      </button>
    </div>
  );
}
