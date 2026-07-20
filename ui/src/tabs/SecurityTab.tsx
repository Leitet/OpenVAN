import { useVan } from "../state";
import { CameraGrid } from "../components/CameraGrid";
import { NoSource } from "../components/NoSource";
import { VanCameraMap } from "../components/VanCameraMap";
import { Security } from "../components/Security";
import { SecuritySensors } from "../components/SecuritySensors";

// Everything security-related in one place: where the cameras are mounted, the live
// camera grid, away-mode arm/disarm, and the sensor/alert status.
export function SecurityTab() {
  const { twin } = useVan();
  const unknown = [
    twin["security.door_open"],
    twin["security.motion"],
    twin["camera.rear.online"],
  ].every((v) => v == null);
  return (
    <div className="tab-grid stack security-tab">
      {unknown && <NoSource />}
      <VanCameraMap />
      <CameraGrid />
      <div className="sec-bottom">
        <Security />
        <SecuritySensors />
      </div>
    </div>
  );
}
