import { sendIntent } from "@shared/api";
import type { Entity } from "@shared/types";

/** On/off + setpoint control for the diesel heater (climate actuator). */
export function HeaterControl({ entity }: { entity: Entity | undefined }) {
  const on = entity?.state === "heating";
  const setpoint =
    typeof entity?.attributes?.setpoint === "number"
      ? (entity.attributes.setpoint as number)
      : 20;

  const toggle = () =>
    sendIntent("climate.diesel_heater", on ? "turn_off" : "turn_on");

  const setTemp = (temperature: number) =>
    sendIntent("climate.diesel_heater", "set_temperature", { temperature });

  return (
    <div className="heater">
      <button
        className={"toggle" + (on ? " on" : "")}
        onClick={toggle}
        disabled={!entity}
      >
        {on ? "Diesel heater: HEATING" : "Diesel heater: OFF"}
      </button>
      <label className="slider">
        <span className="slider-label">
          Setpoint
          <em>{setpoint}°C</em>
        </span>
        <input
          type="range"
          min={5}
          max={30}
          step={0.5}
          value={setpoint}
          onChange={(e) => setTemp(Number(e.target.value))}
        />
      </label>
    </div>
  );
}
