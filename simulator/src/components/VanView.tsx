interface VanViewProps {
  lightOn: boolean;
  heaterOn: boolean;
  soc: number | undefined;
  cabinTemp: number | undefined;
}

/** Simple top-down twin of the van cabin. Grows richer as plugins are added. */
export function VanView({ lightOn, heaterOn, soc, cabinTemp }: VanViewProps) {
  return (
    <svg className="van" viewBox="0 0 300 160" role="img" aria-label="Van floorplan">
      <rect x="8" y="8" width="284" height="144" rx="22" className="van-body" />
      {/* cab */}
      <rect x="20" y="24" width="60" height="112" rx="12" className="van-cab" />
      {/* living space glow when the cabin light is on */}
      <rect
        x="92"
        y="24"
        width="188"
        height="112"
        rx="12"
        className={"van-cabin" + (lightOn ? " lit" : "")}
      />
      <circle cx="186" cy="80" r="9" className={"lamp" + (lightOn ? " on" : "")} />
      <text x="250" y="52" className={"heat" + (heaterOn ? " on" : "")}>
        ≋
      </text>
      <text x="186" y="120" className="van-caption">
        {cabinTemp !== undefined ? `${cabinTemp.toFixed(0)}°C` : ""}
      </text>
      <text x="50" y="84" className="van-caption">
        {soc !== undefined ? `${soc.toFixed(0)}%` : ""}
      </text>
    </svg>
  );
}
