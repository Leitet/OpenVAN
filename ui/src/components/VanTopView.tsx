import { useRef } from "react";

// The van seen from above, front to the left. Cameras are placed in van
// coordinates — x: 0 (front) … 100 (rear) along the length, y: 0 … 100 across
// the width — and aimed with a heading in degrees clockwise from the direction
// of travel (0 = forward, 90 = across, 180 = rearward).
//
// One component, two roles: the Cameras Simulator's settings page uses it as an
// editor (drag the dot to move, drag the arrow to aim), the Security tab as a
// live display (state colours the mount).

export interface PlacedCamera {
  id: string;
  label: string;
  x: number;
  y: number;
  heading: number;
  state?: "on" | "off" | "motion";
}

const VIEW = { w: 360, h: 200 };
const BODY = { x: 42, y: 56, w: 288, h: 88 };

function toSvg(x: number, y: number) {
  return { cx: BODY.x + (x / 100) * BODY.w, cy: BODY.y + (y / 100) * BODY.h };
}

export function VanTopView({
  cameras,
  selected,
  onSelect,
  onMove,
  onAim,
}: {
  cameras: PlacedCamera[];
  selected?: string | null;
  onSelect?: (id: string) => void;
  onMove?: (id: string, x: number, y: number) => void;
  onAim?: (id: string, heading: number) => void;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const dragRef = useRef<{ id: string; mode: "move" | "aim" } | null>(null);
  const editable = Boolean(onMove || onAim);

  const svgPoint = (e: React.PointerEvent) => {
    const r = svgRef.current!.getBoundingClientRect();
    return {
      x: ((e.clientX - r.left) / r.width) * VIEW.w,
      y: ((e.clientY - r.top) / r.height) * VIEW.h,
    };
  };

  const handleMove = (e: React.PointerEvent) => {
    const drag = dragRef.current;
    if (!drag) return;
    const p = svgPoint(e);
    if (drag.mode === "move" && onMove) {
      onMove(
        drag.id,
        Math.max(0, Math.min(100, ((p.x - BODY.x) / BODY.w) * 100)),
        Math.max(0, Math.min(100, ((p.y - BODY.y) / BODY.h) * 100)),
      );
    } else if (drag.mode === "aim" && onAim) {
      const cam = cameras.find((c) => c.id === drag.id);
      if (!cam) return;
      const { cx, cy } = toSvg(cam.x, cam.y);
      // heading such that rotate(heading) applied to "forward" (−1, 0) points
      // at the cursor: θ = atan2(−vy, −vx).
      const deg = (Math.atan2(-(p.y - cy), -(p.x - cx)) * 180) / Math.PI;
      onAim(drag.id, Math.round((deg + 360) % 360));
    }
  };

  const startDrag = (e: React.PointerEvent, id: string, mode: "move" | "aim") => {
    if (!editable) return;
    e.preventDefault();
    dragRef.current = { id, mode };
    onSelect?.(id);
    svgRef.current?.setPointerCapture(e.pointerId);
  };

  return (
    <svg
      ref={svgRef}
      className={"vtv-svg" + (editable ? " editable" : "")}
      viewBox={`0 0 ${VIEW.w} ${VIEW.h}`}
      onPointerMove={handleMove}
      onPointerUp={() => (dragRef.current = null)}
      onPointerLeave={() => (dragRef.current = null)}
    >
      {/* van body, front to the left */}
      <rect className="vtv-van" x={BODY.x} y={BODY.y} width={BODY.w} height={BODY.h} rx={20} />
      {/* windscreen + cab line */}
      <path
        className="vtv-glass"
        d={`M${BODY.x + 34} ${BODY.y + 6} L${BODY.x + 22} ${BODY.y + 22} L${BODY.x + 22} ${BODY.y + BODY.h - 22} L${BODY.x + 34} ${BODY.y + BODY.h - 6} Z`}
      />
      {/* mirrors */}
      <line className="vtv-mirror" x1={BODY.x + 40} y1={BODY.y} x2={BODY.x + 52} y2={BODY.y - 10} />
      <line className="vtv-mirror" x1={BODY.x + 40} y1={BODY.y + BODY.h} x2={BODY.x + 52} y2={BODY.y + BODY.h + 10} />
      <text className="vtv-front" x={BODY.x - 8} y={VIEW.h / 2} textAnchor="end" dominantBaseline="middle">
        ▸
      </text>

      {cameras.map((cam) => {
        const { cx, cy } = toSvg(cam.x, cam.y);
        const cls =
          "vtv-cam state-" + (cam.state ?? "on") + (selected === cam.id ? " selected" : "");
        return (
          <g key={cam.id} className={cls}>
            <g transform={`translate(${cx} ${cy}) rotate(${cam.heading})`}>
              {/* field of view, base pointing forward (−x) */}
              <polygon className="vtv-fov" points="0,0 -34,-15 -34,15" />
              {editable && (
                <circle
                  className="vtv-aim"
                  cx={-30}
                  cy={0}
                  r={5}
                  onPointerDown={(e) => startDrag(e, cam.id, "aim")}
                />
              )}
              <circle
                className="vtv-dot"
                r={6}
                onPointerDown={(e) => startDrag(e, cam.id, "move")}
                onClick={() => onSelect?.(cam.id)}
              />
            </g>
            <text className="vtv-label" x={cx} y={cy - 11} textAnchor="middle">
              {cam.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
