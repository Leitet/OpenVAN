// Cartoon SVG "feed" per camera location, with a fun actor that walks/drives across
// when motion is detected (a car behind the van, a cat in the cabin, a prowler at
// the door, a raccoon by the awning). The day/night filter on .cam-feed re-tints it.

const SPEED: Record<string, string> = { rear: "2.6s", cabin: "4s", door: "4.5s", awning: "3.4s" };

function Rear() {
  return (
    <>
      <rect width="160" height="90" fill="#8ec0ee" />
      <rect y="40" width="160" height="8" fill="#6f9a4d" />
      <polygon points="64,44 96,44 150,90 10,90" fill="#4c535e" />
      <g fill="#ecd44e">
        <rect x="78" y="50" width="4" height="6" />
        <rect x="77" y="62" width="6" height="9" />
        <rect x="74" y="77" width="11" height="11" />
      </g>
      <g className="cam-actor">
        <g transform="translate(0,60)">
          <rect x="0" y="7" width="30" height="12" rx="4" fill="#e0574f" />
          <rect x="6" y="0" width="18" height="9" rx="3" fill="#e0574f" />
          <rect x="8" y="2" width="14" height="6" rx="2" fill="#c7e6f4" />
          <circle cx="7" cy="20" r="3.6" fill="#20242a" />
          <circle cx="23" cy="20" r="3.6" fill="#20242a" />
        </g>
      </g>
    </>
  );
}

function Cabin() {
  return (
    <>
      <rect width="160" height="90" fill="#d9c8a7" />
      <rect y="63" width="160" height="27" fill="#a98f68" />
      <rect x="14" y="14" width="42" height="34" fill="#bfe3f2" stroke="#8a7350" strokeWidth="3" />
      <line x1="35" y1="14" x2="35" y2="48" stroke="#8a7350" strokeWidth="2" />
      <line x1="14" y1="31" x2="56" y2="31" stroke="#8a7350" strokeWidth="2" />
      <g>
        <rect x="104" y="44" width="46" height="22" rx="5" fill="#7e6f8f" />
        <rect x="100" y="50" width="12" height="16" rx="4" fill="#6d5f7d" />
        <rect x="142" y="50" width="12" height="16" rx="4" fill="#6d5f7d" />
      </g>
      <g className="cam-actor">
        <g transform="translate(0,54)">
          <ellipse cx="13" cy="9" rx="11" ry="5" fill="#565661" />
          <circle cx="23" cy="4" r="4.4" fill="#565661" />
          <polygon points="20,1 21,-3 23,1" fill="#565661" />
          <polygon points="24,1 26,-3 27,1" fill="#565661" />
          <path d="M2 8 q-6 -2 -4 -8" stroke="#565661" strokeWidth="3" fill="none" />
          <rect x="6" y="12" width="2.5" height="6" fill="#565661" />
          <rect x="18" y="12" width="2.5" height="6" fill="#565661" />
        </g>
      </g>
    </>
  );
}

function Door() {
  return (
    <>
      <rect width="160" height="90" fill="#9fb6c4" />
      <rect y="70" width="160" height="20" fill="#6d6258" />
      <rect x="52" y="16" width="56" height="62" rx="2" fill="#cbd4da" stroke="#7c8890" strokeWidth="3" />
      <rect x="98" y="46" width="5" height="12" rx="2" fill="#5f6b73" />
      <rect x="40" y="60" width="10" height="18" rx="3" fill="#4f7a45" />
      <ellipse cx="45" cy="58" rx="9" ry="7" fill="#5c8f4f" />
      <g className="cam-actor">
        <g transform="translate(0,40)">
          <circle cx="8" cy="6" r="5" fill="#30353c" />
          <rect x="2" y="4" width="12" height="3" rx="1.5" fill="#20242a" />
          <rect x="3.5" y="11" width="9" height="17" rx="3.5" fill="#30353c" />
          <rect x="4.5" y="27" width="3" height="8" fill="#30353c" />
          <rect x="8.5" y="27" width="3" height="8" fill="#30353c" />
        </g>
      </g>
    </>
  );
}

function Awning() {
  return (
    <>
      <rect width="160" height="90" fill="#8ec6ee" />
      <rect y="58" width="160" height="32" fill="#7a9a5e" />
      <g>
        {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
          <rect key={i} x={i * 20} y="8" width="20" height="14" fill={i % 2 ? "#e6e0d4" : "#d9564e"} />
        ))}
        <rect y="22" width="160" height="3" fill="#b5b0a4" />
      </g>
      <rect x="120" y="30" width="5" height="28" fill="#7a5a3c" />
      <circle cx="122" cy="30" r="12" fill="#5c8f4f" />
      <g className="cam-actor">
        <g transform="translate(0,60)">
          <ellipse cx="13" cy="9" rx="12" ry="6" fill="#8a8f96" />
          <circle cx="24" cy="6" r="5" fill="#9aa0a7" />
          <path d="M20 4 l3 4 l3 -4" fill="#2c2f34" />
          <circle cx="23" cy="6" r="1.3" fill="#20242a" />
          <path d="M2 8 q-8 -1 -6 8" stroke="#6c7178" strokeWidth="4" fill="none" />
          <path d="M2 8 q-8 -1 -6 8" stroke="#3a3d42" strokeWidth="1.5" strokeDasharray="3 3" fill="none" />
          <rect x="6" y="13" width="3" height="6" fill="#8a8f96" />
          <rect x="18" y="13" width="3" height="6" fill="#8a8f96" />
        </g>
      </g>
    </>
  );
}

const SCENES: Record<string, () => JSX.Element> = {
  rear: Rear,
  cabin: Cabin,
  door: Door,
  awning: Awning,
};

export function CameraScene({ location, motion }: { location: string; motion: boolean }) {
  const Scene = SCENES[location] ?? Cabin;
  return (
    <svg
      className={"cam-scene" + (motion ? " motion" : "")}
      viewBox="0 0 160 90"
      preserveAspectRatio="xMidYMid slice"
      style={{ ["--cam-speed" as string]: SPEED[location] ?? "4s" }}
      aria-hidden="true"
    >
      <Scene />
    </svg>
  );
}
