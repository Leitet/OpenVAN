import { CameraGrid } from "../components/CameraGrid";
import { Security } from "../components/Security";
import { SecuritySensors } from "../components/SecuritySensors";

// Everything security-related in one place: live camera grid, away-mode arm/disarm,
// and the sensor/alert status (door, motion, camera motion, intrusion).
export function SecurityTab() {
  return (
    <div className="tab-grid stack security-tab">
      <CameraGrid />
      <div className="sec-bottom">
        <Security />
        <SecuritySensors />
      </div>
    </div>
  );
}
