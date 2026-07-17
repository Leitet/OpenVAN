import { useEffect, useState } from "react";
import { ShieldCheck, Shield } from "lucide-react";
import { getSecurity, setSecurity } from "@shared/api";
import { useT } from "../i18n";

// Away mode: arm when you leave the van; while armed, a door or motion event
// raises a security notice (handled by Core's Intrusion advisor).
export function Security() {
  const t = useT();
  const [armed, setArmed] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getSecurity().then((s) => setArmed(s.armed));
  }, []);

  const toggle = async () => {
    setBusy(true);
    try {
      const s = await setSecurity(!armed);
      setArmed(s.armed);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel security">
      <h2>{t("security.title")}</h2>
      <button
        className={"security-btn" + (armed ? " armed" : "")}
        disabled={busy || armed === null}
        onClick={toggle}
      >
        <span className="security-icon">{armed ? <ShieldCheck /> : <Shield />}</span>
        <span>{armed ? t("security.armed") : t("security.disarmed")}</span>
        <small>{armed ? t("security.tapDisarm") : t("security.tapArm")}</small>
      </button>
    </section>
  );
}
