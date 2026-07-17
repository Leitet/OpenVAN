import { useVan } from "../state";
import { Journey } from "../components/Journey";
import { Weather } from "../components/Weather";
import { Journal } from "../components/Journal";
import { Leveling } from "../components/Leveling";

export function JourneyTab() {
  const { twin } = useVan();
  return (
    <div className="tab-grid stack journey-tab">
      <Journey twin={twin} />
      <Leveling />
      <Weather />
      <Journal />
    </div>
  );
}
