import { CameraGrid } from "../components/CameraGrid";
import { VanCameraMap } from "../components/VanCameraMap";
import { Security } from "../components/Security";
import { SecuritySensors } from "../components/SecuritySensors";

// Everything security-related in one place: where the cameras are mounted, the live
// camera grid, away-mode arm/disarm, and the sensor/alert status.
export function SecurityTab() {
  return (
    <div className="tab-grid stack security-tab">
      <VanCameraMap />
      <CameraGrid />
      <div className="sec-bottom">
        <Security />
        <SecuritySensors />
      </div>
    </div>
  );
}
