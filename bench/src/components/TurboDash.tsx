import { useCallback, useEffect, useRef, useState } from "react";
import "./turbodash.css";

// ── Turnin' Turbo Dashboard ─────────────────────────────────────────────────
// A love-letter to the 1983 Tomy toy: a steering wheel, a scrolling neon road,
// and random cars to pass. It's a *bench* toy — but it drives the real twin: the
// throttle sets `vehicle.speed_kmh`, the wheel integrates `vehicle.heading`, and
// the key toggles `vehicle.ignition`. So Core still dead-reckons the van along
// its heading and the product-UI map traces exactly as before — only the
// controls got a lot more fun.

type Signal = (key: string, value: number | boolean) => void;

interface Props {
  speed: number;
  ignition: boolean;
  heading: number;
  onSignal: Signal;
}

// Pseudo-3D road projection constants (Jake-Gordon style, tuned for the toy look).
const FOV = 100;
const CAM_D = 1 / Math.tan(((FOV / 2) * Math.PI) / 180); // camera depth
const CAM_H = 1000; // camera height above the road
const SEG = 200; // world length of one road segment
const ROAD_W = 2000; // world half-width of the road
const DRAW = 120; // segments drawn ahead
const MAX_SPEED = 130; // km/h — matches the old slider ceiling
const MAX_WHEEL = 2.4; // radians of lock, each way (~137°)
const TURN_RATE = 95; // deg/sec of heading change at full lock + full speed
const POS_K = 11; // km/h → world units/sec (scroll feel)

const CAR_COLORS = ["#ff5252", "#4b7bec", "#f7b731", "#26de81", "#e056fd", "#ffffff"];

interface Car {
  z: number; // absolute world Z
  lane: number; // -0.7 .. 0.7 across the road
  color: string;
}

function makeCars(): Car[] {
  // Deterministic seed spread so they don't all clump (no Math.random at import).
  return Array.from({ length: 6 }, (_, i) => ({
    z: 1500 + i * 2200,
    lane: [-0.55, 0.5, -0.2, 0.6, -0.6, 0.25][i],
    color: CAR_COLORS[i % CAR_COLORS.length],
  }));
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  const rr = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.arcTo(x + w, y, x + w, y + h, rr);
  ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr);
  ctx.arcTo(x, y, x + w, y, rr);
  ctx.closePath();
}

function drawCar(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, color: string, player = false) {
  const h = w * 0.92;
  const top = y - h;
  ctx.save();
  ctx.fillStyle = "rgba(0,0,0,.28)";
  ctx.beginPath();
  ctx.ellipse(x, y, w * 0.55, h * 0.13, 0, 0, Math.PI * 2);
  ctx.fill();
  // body
  ctx.fillStyle = color;
  roundRect(ctx, x - w / 2, top, w, h, w * 0.16);
  ctx.fill();
  // cabin highlight
  ctx.fillStyle = "rgba(255,255,255,.16)";
  roundRect(ctx, x - w * 0.34, top + h * 0.1, w * 0.68, h * 0.42, w * 0.1);
  ctx.fill();
  // rear window
  ctx.fillStyle = "rgba(15,15,40,.8)";
  roundRect(ctx, x - w * 0.29, top + h * 0.15, w * 0.58, h * 0.27, w * 0.08);
  ctx.fill();
  // lights
  if (player) {
    ctx.fillStyle = "#fff7c0";
    ctx.fillRect(x - w * 0.42, top + h * 0.02, w * 0.16, h * 0.1);
    ctx.fillRect(x + w * 0.26, top + h * 0.02, w * 0.16, h * 0.1);
  } else {
    ctx.fillStyle = "#ff3b3b";
    ctx.fillRect(x - w * 0.44, top + h * 0.74, w * 0.15, h * 0.12);
    ctx.fillRect(x + w * 0.29, top + h * 0.74, w * 0.15, h * 0.12);
  }
  ctx.restore();
}

export function TurboDash({ speed, ignition, heading, onSignal }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  // Mutable sim state — lives in a ref so the rAF loop never triggers re-renders.
  const sim = useRef({
    pos: 0,
    speed: 0,
    ignition: false,
    heading: 0,
    wheel: 0, // radians, current wheel rotation
    throttle: 0,
    brake: 0,
    dragging: false,
    dragStart: 0,
    dragWheel: 0,
    cars: makeCars(),
    passed: 0,
    lastInjSpeed: -1,
    lastInjHeading: -1,
    lastInjAt: 0,
    prevT: 0,
  });
  const keys = useRef<Set<string>>(new Set());

  // HUD state (throttled updates from the loop — a few times a second).
  const [hud, setHud] = useState({ speed: 0, heading: 0, passed: 0, ignition: false, wheelDeg: 0, gear: "P" });
  const hudAt = useRef(0);

  // Seed the sim from the twin once, and keep ignition in sync if it changes
  // externally (e.g. a scenario button).
  useEffect(() => {
    sim.current.speed = speed || 0;
    sim.current.heading = heading || 0;
    sim.current.ignition = ignition;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    sim.current.ignition = ignition;
  }, [ignition]);

  // ── the drive loop ────────────────────────────────────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d")!;
    let raf = 0;
    let dpr = Math.min(window.devicePixelRatio || 1, 2);

    const resize = () => {
      const el = wrapRef.current!;
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(el.clientWidth * dpr);
      canvas.height = Math.round(el.clientHeight * dpr);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(wrapRef.current!);

    const frame = (t: number) => {
      const s = sim.current;
      const dt = s.prevT ? Math.min(0.05, (t - s.prevT) / 1000) : 0.016;
      s.prevT = t;

      // keyboard → controls
      const k = keys.current;
      const gas = k.has("ArrowUp") || k.has("w");
      const brk = k.has("ArrowDown") || k.has("s") || k.has(" ");
      s.throttle = gas ? 1 : Math.max(0, s.throttle - dt * 3);
      s.brake = brk ? 1 : 0;
      if (!s.dragging) {
        if (k.has("ArrowLeft") || k.has("a")) s.wheel = Math.max(-MAX_WHEEL, s.wheel - dt * 3.5);
        else if (k.has("ArrowRight") || k.has("d")) s.wheel = Math.min(MAX_WHEEL, s.wheel + dt * 3.5);
        else s.wheel += (0 - s.wheel) * Math.min(1, dt * 4); // spring back to centre
      }
      const steer = s.wheel / MAX_WHEEL;

      // engine model
      if (s.ignition) {
        const target = s.throttle * MAX_SPEED;
        if (s.throttle > 0) s.speed += (target - s.speed) * Math.min(1, dt * 1.3);
        s.speed -= s.brake * 90 * dt;
        s.speed -= 7 * dt; // rolling drag
      } else {
        s.speed -= 40 * dt;
      }
      s.speed = Math.max(0, Math.min(MAX_SPEED, s.speed));

      // integrate heading like a real van: only turns while rolling
      const speedFrac = s.speed / MAX_SPEED;
      s.heading += steer * TURN_RATE * speedFrac * dt;
      s.heading = ((s.heading % 360) + 360) % 360;

      // roll the world
      s.pos += s.speed * POS_K * dt;

      // recycle cars we've passed
      for (const car of s.cars) {
        if (car.z - s.pos < -SEG * 2) {
          car.z = s.pos + DRAW * SEG * (0.45 + 0.5 * ((s.passed * 37) % 100) / 100);
          car.lane = (((s.passed * 53) % 130) - 65) / 100; // -0.65..0.65, deterministic
          car.color = CAR_COLORS[s.passed % CAR_COLORS.length];
          s.passed += 1;
        }
      }

      render(ctx, canvas, dpr, s, steer);
      pushSignals(s, t);

      // throttle HUD
      if (t - hudAt.current > 90) {
        hudAt.current = t;
        const gear = !s.ignition ? "P" : s.speed < 1 ? "N" : "D";
        setHud({
          speed: Math.round(s.speed),
          heading: Math.round(s.heading),
          passed: s.passed,
          ignition: s.ignition,
          wheelDeg: (s.wheel * 180) / Math.PI,
          gear,
        });
      }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pushSignals = (s: typeof sim.current, t: number) => {
    if (t - s.lastInjAt < 100) return;
    s.lastInjAt = t;
    const sp = Math.round(s.speed);
    if (sp !== s.lastInjSpeed) {
      onSignal("vehicle.speed_kmh", sp);
      s.lastInjSpeed = sp;
    }
    const hd = Math.round(s.heading);
    if (hd !== s.lastInjHeading) {
      onSignal("vehicle.heading", hd);
      s.lastInjHeading = hd;
    }
  };

  // ── rendering ─────────────────────────────────────────────────────────────
  function render(
    ctx: CanvasRenderingContext2D,
    canvas: HTMLCanvasElement,
    dpr: number,
    s: typeof sim.current,
    steer: number,
  ) {
    const W = canvas.width / dpr;
    const H = canvas.height / dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const horizon = H * 0.5;

    // sky
    const sky = ctx.createLinearGradient(0, 0, 0, horizon);
    sky.addColorStop(0, "#160a2e");
    sky.addColorStop(0.55, "#3b1258");
    sky.addColorStop(1, "#c02a6e");
    ctx.fillStyle = sky;
    ctx.fillRect(0, 0, W, horizon);

    // synthwave sun with scanlines
    const sunR = H * 0.26;
    const sunCx = W / 2 - steer * W * 0.12;
    const sunCy = horizon - sunR * 0.15;
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, 0, W, horizon);
    ctx.clip();
    const sun = ctx.createLinearGradient(0, sunCy - sunR, 0, sunCy + sunR);
    sun.addColorStop(0, "#ffe36a");
    sun.addColorStop(0.5, "#ff9a3c");
    sun.addColorStop(1, "#ff3d7f");
    ctx.fillStyle = sun;
    ctx.beginPath();
    ctx.arc(sunCx, sunCy, sunR, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#160a2e";
    for (let i = 0; i < 7; i++) {
      const yy = sunCy + sunR * 0.12 + i * (sunR * 0.16);
      ctx.fillRect(sunCx - sunR, yy, sunR * 2, Math.max(2, sunR * 0.05 + i));
    }
    ctx.restore();

    // ground
    ctx.fillStyle = "#0c331d";
    ctx.fillRect(0, horizon, W, H - horizon);

    // project the road segments (near → far), accumulating curve from the wheel
    const curve = steer * 2.2;
    const base = Math.floor(s.pos / SEG);
    const basePercent = (s.pos % SEG) / SEG;
    let x = 0;
    let dx = -(curve * basePercent);

    type Edge = { y: number; cx: number; w: number; scale: number };
    const edges: Edge[] = [];
    for (let n = 0; n <= DRAW; n++) {
      const camZ = (base + n) * SEG - s.pos;
      const cz = Math.max(camZ, 1);
      const scale = CAM_D / cz;
      const cx = W / 2 + scale * x * (W / 2) * 0.5;
      const y = horizon + scale * CAM_H * (H / 2) * 0.5;
      const w = scale * ROAD_W * (W / 2) * 0.5;
      edges.push({ y, cx, w, scale });
      x += dx;
      dx += curve;
    }

    // draw far → near so nearer road paints over the horizon
    for (let n = DRAW; n >= 1; n--) {
      const far = edges[n];
      const near = edges[n - 1];
      if (near.y <= horizon) continue;
      const idx = base + n;
      const light = (idx & 1) === 0;
      // grass band (alternating shades = the classic scrolling speed cue)
      ctx.fillStyle = light ? "#0f6b39" : "#0c5730";
      ctx.fillRect(0, far.y, W, near.y - far.y + 1);
      // rumble strips
      poly(ctx, near.cx, near.y, near.w * 1.16, far.cx, far.y, far.w * 1.16, light ? "#ffffff" : "#c0143c");
      // road
      poly(ctx, near.cx, near.y, near.w, far.cx, far.y, far.w, light ? "#43434f" : "#3b3b46");
      // centre dashes on light segments
      if (light) {
        poly(ctx, near.cx, near.y, near.w * 0.05, far.cx, far.y, far.w * 0.05, "#f7d000");
      }
    }

    // traffic — placed on the projected road edge nearest their depth, so they
    // ride the curve of the road as it bends with the wheel.
    const sorted = [...s.cars].sort((a, b) => b.z - a.z); // far first (painter)
    for (const car of sorted) {
      const camZ = car.z - s.pos;
      if (camZ < 1 || camZ > DRAW * SEG) continue;
      const n = Math.min(DRAW, Math.max(0, Math.round(camZ / SEG + basePercent)));
      const e = edges[n];
      const scale = CAM_D / camZ;
      const cx = e.cx + scale * (car.lane * ROAD_W) * (W / 2) * 0.5;
      // Cap the size so a car we're passing doesn't swallow the whole screen.
      const cw = Math.min(W * 0.24, scale * 1300 * (W / 2) * 0.5);
      if (cw < 2) continue;
      drawCar(ctx, cx, e.y, cw, car.color);
    }

    // player van, fixed near the bottom, leaning with the wheel
    drawCar(ctx, W / 2 + steer * W * 0.05, H * 0.99, W * 0.15, "#ff7a1a", true);

    // speed streaks when going fast
    if (s.speed > 70) {
      ctx.strokeStyle = "rgba(255,255,255,.35)";
      ctx.lineWidth = 2;
      const streaks = 6;
      for (let i = 0; i < streaks; i++) {
        const sx = ((i * 131 + (s.pos * 3) % 400) % W);
        ctx.beginPath();
        ctx.moveTo(sx, H * 0.6);
        ctx.lineTo(sx, H * 0.6 + (s.speed - 70) * 0.8);
        ctx.stroke();
      }
    }
  }

  function poly(
    ctx: CanvasRenderingContext2D,
    x1: number,
    y1: number,
    w1: number,
    x2: number,
    y2: number,
    w2: number,
    color: string,
  ) {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(x1 - w1, y1);
    ctx.lineTo(x1 + w1, y1);
    ctx.lineTo(x2 + w2, y2);
    ctx.lineTo(x2 - w2, y2);
    ctx.closePath();
    ctx.fill();
  }

  // ── controls ──────────────────────────────────────────────────────────────
  const toggleIgnition = () => {
    const next = !sim.current.ignition;
    sim.current.ignition = next;
    onSignal("vehicle.ignition", next);
    setHud((h) => ({ ...h, ignition: next }));
  };

  const onWheelDown = useCallback((e: React.PointerEvent) => {
    const el = e.currentTarget as HTMLElement;
    el.setPointerCapture(e.pointerId);
    const r = el.getBoundingClientRect();
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height / 2;
    sim.current.dragging = true;
    sim.current.dragStart = Math.atan2(e.clientY - cy, e.clientX - cx);
    sim.current.dragWheel = sim.current.wheel;
  }, []);
  const onWheelMove = useCallback((e: React.PointerEvent) => {
    if (!sim.current.dragging) return;
    const el = e.currentTarget as HTMLElement;
    const r = el.getBoundingClientRect();
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height / 2;
    const a = Math.atan2(e.clientY - cy, e.clientX - cx);
    let d = a - sim.current.dragStart;
    while (d > Math.PI) d -= Math.PI * 2;
    while (d < -Math.PI) d += Math.PI * 2;
    sim.current.wheel = Math.max(-MAX_WHEEL, Math.min(MAX_WHEEL, sim.current.dragWheel + d));
  }, []);
  const onWheelUp = useCallback(() => {
    sim.current.dragging = false;
  }, []);

  const gasDown = () => (sim.current.throttle = 1);
  const gasUp = () => (sim.current.throttle = 0);
  const brakeDown = () => (sim.current.brake = 1);
  const brakeUp = () => (sim.current.brake = 0);

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", " "].includes(e.key)) e.preventDefault();
      keys.current.add(e.key);
    };
    const up = (e: KeyboardEvent) => keys.current.delete(e.key);
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, []);

  const needle = -120 + (hud.speed / MAX_SPEED) * 240; // -120°..+120°

  return (
    <div className="turbo">
      <div className="turbo-screen" ref={wrapRef}>
        <canvas ref={canvasRef} />
        <div className="turbo-hud">
          <span className={"gear g-" + hud.gear}>{hud.gear}</span>
          <span className="passed">🏁 {hud.passed} passed</span>
          <span className="hdg">{hud.heading}°</span>
        </div>
      </div>

      <div className="turbo-controls">
        <button
          className={"ignition" + (hud.ignition ? " on" : "")}
          onClick={toggleIgnition}
          title="Ignition"
        >
          <span className="key-slot" />
          {hud.ignition ? "ENGINE ON" : "START"}
        </button>

        <div className="wheel-wrap">
          <svg
            className="wheel"
            viewBox="-50 -50 100 100"
            style={{ transform: `rotate(${hud.wheelDeg}deg)` }}
            onPointerDown={onWheelDown}
            onPointerMove={onWheelMove}
            onPointerUp={onWheelUp}
            onPointerCancel={onWheelUp}
          >
            <circle r="46" className="rim" />
            <circle r="34" className="rim-inner" />
            <circle r="12" className="hub" />
            <rect x="-4" y="-46" width="8" height="34" className="spoke" />
            <rect x="-46" y="-4" width="34" height="8" className="spoke" />
            <rect x="12" y="-4" width="34" height="8" className="spoke" />
            <circle r="4" cx="0" cy="-40" className="grip" />
          </svg>
          <span className="wheel-label">STEER — drag or ← →</span>
        </div>

        <div className="speedo">
          <svg viewBox="-50 -50 100 60">
            {Array.from({ length: 9 }, (_, i) => {
              const ang = (-120 + i * 30) * (Math.PI / 180);
              return (
                <line
                  key={i}
                  x1={Math.cos(ang) * 40}
                  y1={Math.sin(ang) * 40}
                  x2={Math.cos(ang) * 46}
                  y2={Math.sin(ang) * 46}
                  className="tick"
                />
              );
            })}
            <line x1="0" y1="0" x2="0" y2="-40" className="needle" style={{ transform: `rotate(${needle}deg)` }} />
            <circle r="4" className="needle-hub" />
          </svg>
          <div className="speedo-read">
            <strong>{hud.speed}</strong>
            <span>km/h</span>
          </div>
        </div>

        <div className="pedals">
          <button
            className="pedal gas"
            onPointerDown={gasDown}
            onPointerUp={gasUp}
            onPointerLeave={gasUp}
            onPointerCancel={gasUp}
          >
            GAS<br />▲
          </button>
          <button
            className="pedal brake"
            onPointerDown={brakeDown}
            onPointerUp={brakeUp}
            onPointerLeave={brakeUp}
            onPointerCancel={brakeUp}
          >
            BRAKE<br />▼
          </button>
        </div>
      </div>
    </div>
  );
}
