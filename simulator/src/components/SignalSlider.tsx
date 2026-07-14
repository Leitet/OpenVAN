import { injectSignal } from "../api";

interface SignalSliderProps {
  label: string;
  signalKey: string;
  value: number | undefined;
  min: number;
  max: number;
  step?: number;
  unit?: string;
}

/**
 * A slider that injects a raw hardware signal into the digital twin — this is
 * how we play "physical world" while there is no real van. Core sees exactly
 * what it would see from a real sensor.
 */
export function SignalSlider({
  label,
  signalKey,
  value,
  min,
  max,
  step = 1,
  unit,
}: SignalSliderProps) {
  const v = typeof value === "number" ? value : min;
  return (
    <label className="slider">
      <span className="slider-label">
        {label}
        <em>
          {v}
          {unit ?? ""}
        </em>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={v}
        onChange={(e) => injectSignal(signalKey, Number(e.target.value))}
      />
    </label>
  );
}
