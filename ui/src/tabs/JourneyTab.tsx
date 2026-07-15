import { useVan } from "../state";
import { Journey } from "../components/Journey";
import { Weather } from "../components/Weather";
import { Journal } from "../components/Journal";

export function JourneyTab() {
  const { twin } = useVan();
  return (
    <div className="tab-grid stack journey-tab">
      <Journey twin={twin} />
      <Weather />
      <Journal />
    </div>
  );
}
