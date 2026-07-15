import { NavIcon } from "./NavIcon";

interface QuickToggleProps {
  icon: string;
  label: string;
  state: string;
  on: boolean;
  disabled?: boolean;
  onClick: () => void;
}

/** A big, touch-friendly on/off action tile for the product UI. */
export function QuickToggle({ icon, label, state, on, disabled, onClick }: QuickToggleProps) {
  return (
    <button
      className={"quick" + (on ? " on" : "")}
      onClick={onClick}
      disabled={disabled}
    >
      <span className="quick-ico">
        <NavIcon name={icon} />
      </span>
      <span className="quick-body">
        <span className="quick-label">{label}</span>
        <span className="quick-state">{state}</span>
      </span>
    </button>
  );
}
