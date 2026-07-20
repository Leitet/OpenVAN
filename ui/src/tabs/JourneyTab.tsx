import { useVan } from "../state";
import { Journey } from "../components/Journey";
import { NoSource } from "../components/NoSource";
import { Trip } from "../components/Trip";
import { Weather } from "../components/Weather";
import { Journal } from "../components/Journal";
import { Leveling } from "../components/Leveling";

export function JourneyTab() {
  const { twin } = useVan();
  return (
    <div className="tab-grid stack journey-tab">
      {[twin["gps.lat"], twin["gps.lon"]].every((v) => v == null) && <NoSource />}
      <Journey twin={twin} />
      <Trip />
      <Leveling />
      <Weather />
      <Journal />
    </div>
  );
}
