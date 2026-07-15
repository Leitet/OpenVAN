# OpenVan components — source reference

Reference implementations for the OpenVan design-system React components. They
read CSS custom properties only (import nothing but React). Copy into your app
and adapt to your conventions; the `.d.ts` prop contracts are included per
component. See README.md for the two-layer model and token values.


## core

### Badge

```tsx
// Badge.d.ts
import React from 'react';
export interface BadgeProps {
  children?: React.ReactNode;
  tone?: 'accent' | 'soft' | 'neutral' | 'outline';
  /** optional leading Lucide icon */
  icon?: string;
  size?: 'sm' | 'md';
  style?: React.CSSProperties;
}
export function Badge(props: BadgeProps): JSX.Element;
```

```jsx
// Badge.jsx
import React from 'react';
import { Icon } from './Icon.jsx';

/**
 * Badge — small status/label pill. Used for the persona tagline chip,
 * connection status, and inline labels. `tone` sets the color treatment.
 */
export function Badge({ children, tone = 'accent', icon, size = 'md', style = {} }) {
  const sizes = {
    sm: { pad: '3px 9px', font: 'var(--ov-text-2xs)', ic: 12, gap: 4 },
    md: { pad: '5px 12px', font: 'var(--ov-text-xs)', ic: 14, gap: 5 },
  }[size];
  const tones = {
    accent: { background: 'var(--ov-accent)', color: 'var(--ov-on-accent)' },
    soft: { background: 'var(--ov-accent-soft)', color: 'var(--ov-accent)' },
    neutral: { background: 'var(--ov-surface-2)', color: 'var(--ov-text-muted)' },
    outline: { background: 'transparent', color: 'var(--ov-accent)', boxShadow: 'inset 0 0 0 1.5px var(--ov-accent)' },
  }[tone];
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: sizes.gap, padding: sizes.pad,
      borderRadius: 'var(--ov-radius-pill)', fontFamily: 'var(--ov-font-body)', fontWeight: 'var(--ov-w-bold)',
      fontSize: sizes.font, letterSpacing: '.04em', textTransform: 'uppercase', lineHeight: 1,
      ...tones, ...style,
    }}>
      {icon && <Icon name={icon} size={sizes.ic} />}
      {children}
    </span>
  );
}
```

### Button

```tsx
// Button.d.ts
import React from 'react';
export interface ButtonProps {
  children?: React.ReactNode;
  /** primary = accent fill · secondary = accent outline · ghost = text only */
  variant?: 'primary' | 'secondary' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  /** Lucide icon name shown before the label */
  icon?: string;
  /** Lucide icon name shown after the label */
  iconRight?: string;
  disabled?: boolean;
  onClick?: (e: React.MouseEvent) => void;
  type?: 'button' | 'submit' | 'reset';
  style?: React.CSSProperties;
}
export function Button(props: ButtonProps): JSX.Element;
```

```jsx
// Button.jsx
import React from 'react';
import { Icon } from './Icon.jsx';

/**
 * Button — OpenVan's primary action control. Pill-shaped, warm.
 * Variants: primary (accent fill), secondary (accent outline), ghost (text only).
 */
export function Button({
  children,
  variant = 'primary',
  size = 'md',
  icon,
  iconRight,
  disabled = false,
  onClick,
  type = 'button',
  style = {},
  ...rest
}) {
  const sizes = {
    sm: { pad: '8px 16px', font: 'var(--ov-text-sm)', gap: 6, ic: 16 },
    md: { pad: '11px 22px', font: 'var(--ov-text-base)', gap: 8, ic: 18 },
    lg: { pad: '15px 30px', font: 'var(--ov-text-lg)', gap: 10, ic: 20 },
  }[size];

  const base = {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: sizes.gap,
    fontFamily: 'var(--ov-font-body)', fontWeight: 'var(--ov-w-bold)', fontSize: sizes.font,
    lineHeight: 1, letterSpacing: '.01em', padding: sizes.pad, borderRadius: 'var(--ov-radius-pill)',
    cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.5 : 1,
    border: '2px solid transparent', transition: 'transform .12s ease, background .16s ease, border-color .16s ease, opacity .16s ease',
    userSelect: 'none', whiteSpace: 'nowrap',
  };

  const variants = {
    primary: { background: 'var(--ov-accent)', color: 'var(--ov-on-accent)' },
    secondary: { background: 'transparent', color: 'var(--ov-accent)', borderColor: 'var(--ov-accent)' },
    ghost: { background: 'transparent', color: 'var(--ov-text)' },
  }[variant];

  const [hover, setHover] = React.useState(false);
  const [press, setPress] = React.useState(false);
  const hoverStyle = !disabled && hover ? (
    variant === 'primary' ? { filter: 'brightness(1.06)' } :
    { background: 'var(--ov-accent-soft)' }
  ) : {};

  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => { setHover(false); setPress(false); }}
      onMouseDown={() => setPress(true)}
      onMouseUp={() => setPress(false)}
      style={{ ...base, ...variants, ...hoverStyle, transform: press && !disabled ? 'scale(.97)' : 'scale(1)', ...style }}
      {...rest}
    >
      {icon && <Icon name={icon} size={sizes.ic} />}
      {children}
      {iconRight && <Icon name={iconRight} size={sizes.ic} />}
    </button>
  );
}
```

### Card

```tsx
// Card.d.ts
import React from 'react';
export interface CardProps {
  children?: React.ReactNode;
  /** surface (default) or the inset surface-2 tone */
  tone?: 'surface' | 'surface-2';
  /** apply default inner padding */
  pad?: boolean;
  radius?: 'md' | 'lg' | 'xl';
  elevation?: 'none' | 'sm' | 'md' | 'lg';
  style?: React.CSSProperties;
}
export function Card(props: CardProps): JSX.Element;
```

```jsx
// Card.jsx
import React from 'react';

/**
 * Card — the persona-card shell and generic surface. Rounded, soft-shadowed,
 * uses the theme surface color. `pad` toggles inner padding; `tone` picks
 * surface vs. inset surface-2.
 */
export function Card({ children, tone = 'surface', pad = true, radius = 'xl', elevation = 'md', style = {}, ...rest }) {
  const bg = tone === 'surface-2' ? 'var(--ov-surface-2)' : 'var(--ov-surface)';
  const shadow = { none: 'none', sm: 'var(--ov-shadow-sm)', md: 'var(--ov-shadow-md)', lg: 'var(--ov-shadow-lg)' }[elevation];
  const rad = { md: 'var(--ov-radius-md)', lg: 'var(--ov-radius-lg)', xl: 'var(--ov-radius-xl)' }[radius];
  return (
    <div
      style={{
        background: bg, color: 'var(--ov-text)', borderRadius: rad,
        border: '1px solid var(--ov-border)', boxShadow: shadow,
        padding: pad ? 'var(--ov-space-6)' : 0, ...style,
      }}
      {...rest}
    >
      {children}
    </div>
  );
}
```

### Gauge

```tsx
// Gauge.d.ts
import React from 'react';
export interface GaugeProps {
  /** 0–100 */
  value?: number;
  variant?: 'bar' | 'ring';
  /** ring diameter in px (ring only) */
  size?: number;
  /** bar height / ring stroke width */
  thickness?: number;
  /** fill color; defaults to --ov-accent */
  color?: string;
  /** track color; defaults to --ov-surface-2 */
  track?: string;
  /** centered caption inside a ring */
  label?: string;
  style?: React.CSSProperties;
}
export function Gauge(props: GaugeProps): JSX.Element;
```

```jsx
// Gauge.jsx
import React from 'react';

/**
 * Gauge — a vitals level indicator (battery/water/solar/tank).
 * variant "bar" = slim rounded track; "ring" = circular dial.
 * `value` 0–100. Fills with accent unless `color` overrides.
 */
export function Gauge({ value = 0, variant = 'bar', size = 64, thickness, color, track, label, style = {} }) {
  const v = Math.max(0, Math.min(100, value));
  const fill = color || 'var(--ov-accent)';
  const trk = track || 'var(--ov-surface-2)';

  if (variant === 'ring') {
    const t = thickness || 7;
    const r = (size - t) / 2;
    const c = 2 * Math.PI * r;
    return (
      <div style={{ position: 'relative', width: size, height: size, ...style }}>
        <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={trk} strokeWidth={t} />
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={fill} strokeWidth={t}
            strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - v / 100)}
            style={{ transition: 'stroke-dashoffset .5s ease' }} />
        </svg>
        <div style={{
          position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', gap: 1,
        }}>
          <span style={{ fontFamily: 'var(--ov-font-mono)', fontWeight: 'var(--ov-w-bold)', fontSize: size * 0.26, color: 'var(--ov-text)', lineHeight: 1 }}>{v}</span>
          {label && <span style={{ fontFamily: 'var(--ov-font-body)', fontSize: size * 0.12, color: 'var(--ov-text-muted)', textTransform: 'uppercase', letterSpacing: '.1em' }}>{label}</span>}
        </div>
      </div>
    );
  }

  const t = thickness || 8;
  return (
    <div style={{ width: '100%', ...style }}>
      <div style={{ height: t, borderRadius: 999, background: trk, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${v}%`, background: fill, borderRadius: 999, transition: 'width .5s ease' }} />
      </div>
    </div>
  );
}
```

### Icon

```tsx
// Icon.d.ts
import React from 'react';
export interface IconProps {
  /** Lucide icon name, e.g. "mountain", "heart", "battery", "sun". */
  name: string;
  /** Pixel size (width & height). Default 24. */
  size?: number;
  /** Stroke width. Default 2. */
  strokeWidth?: number;
  /** Color override; defaults to currentColor. */
  color?: string;
  style?: React.CSSProperties;
  className?: string;
}
export function Icon(props: IconProps): JSX.Element;
```

```jsx
// Icon.jsx
import React from 'react';

/**
 * Icon — thin wrapper over Lucide (loaded from CDN as window.lucide).
 * Renders a single line icon that inherits the current text color.
 * Substitution note: OpenVan's source ships no icon set, so the DS uses
 * Lucide (matching the clean 2px-stroke look of the persona cards).
 */
export function Icon({ name, size = 24, strokeWidth = 2, color = 'currentColor', style = {}, className = '' }) {
  const ref = React.useRef(null);
  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.innerHTML = '';
    const i = document.createElement('i');
    i.setAttribute('data-lucide', name);
    el.appendChild(i);
    if (window.lucide && window.lucide.createIcons) {
      window.lucide.createIcons({ attrs: { width: size, height: size, 'stroke-width': strokeWidth } });
    }
  }, [name, size, strokeWidth]);
  return (
    <span
      ref={ref}
      className={className}
      aria-hidden="true"
      style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', color, lineHeight: 0, ...style }}
    />
  );
}
```

### IconButton

```tsx
// IconButton.d.ts
import React from 'react';
export interface IconButtonProps {
  /** Lucide icon name */
  icon: string;
  variant?: 'soft' | 'solid' | 'ghost' | 'outline';
  size?: 'sm' | 'md' | 'lg';
  shape?: 'circle' | 'rounded';
  disabled?: boolean;
  onClick?: (e: React.MouseEvent) => void;
  /** Accessible label (aria-label) */
  label?: string;
  style?: React.CSSProperties;
}
export function IconButton(props: IconButtonProps): JSX.Element;
```

```jsx
// IconButton.jsx
import React from 'react';
import { Icon } from './Icon.jsx';

/**
 * IconButton — square/round icon-only control. Used for audio-play chips,
 * toolbar actions, and compact controls on persona cards.
 */
export function IconButton({
  icon,
  variant = 'soft',
  size = 'md',
  shape = 'circle',
  disabled = false,
  onClick,
  label,
  style = {},
  ...rest
}) {
  const dims = { sm: 30, md: 38, lg: 46 }[size];
  const ic = { sm: 15, md: 18, lg: 22 }[size];
  const variants = {
    soft: { background: 'var(--ov-accent-soft)', color: 'var(--ov-accent)', border: '1px solid var(--ov-border)' },
    solid: { background: 'var(--ov-accent)', color: 'var(--ov-on-accent)', border: '1px solid transparent' },
    ghost: { background: 'transparent', color: 'var(--ov-text)', border: '1px solid transparent' },
    outline: { background: 'transparent', color: 'var(--ov-accent)', border: '1.5px solid var(--ov-accent)' },
  }[variant];
  const [hover, setHover] = React.useState(false);
  const [press, setPress] = React.useState(false);
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => { setHover(false); setPress(false); }}
      onMouseDown={() => setPress(true)}
      onMouseUp={() => setPress(false)}
      style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: dims, height: dims, flex: `0 0 ${dims}px`,
        borderRadius: shape === 'circle' ? '999px' : 'var(--ov-radius-md)',
        cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.5 : 1,
        transition: 'transform .12s ease, filter .16s ease, background .16s ease',
        transform: press && !disabled ? 'scale(.92)' : 'scale(1)',
        filter: hover && !disabled ? 'brightness(1.06)' : 'none',
        ...variants, ...style,
      }}
      {...rest}
    >
      <Icon name={icon} size={ic} />
    </button>
  );
}
```

## persona

### CapabilityTile

```tsx
// CapabilityTile.d.ts
import React from 'react';
export interface CapabilityTileProps {
  /** Lucide icon */
  icon: string;
  /** short caption, e.g. "Scenic Route Finder" */
  label: string;
  style?: React.CSSProperties;
}
export function CapabilityTile(props: CapabilityTileProps): JSX.Element;
```

```jsx
// CapabilityTile.jsx
import React from 'react';
import { Icon } from '../core/Icon.jsx';

/**
 * CapabilityTile — one item in the "WHAT X DOES BEST" row: a large accent
 * icon above a short centered label (1–2 lines).
 */
export function CapabilityTile({ icon, label, style = {} }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--ov-space-2)',
      textAlign: 'center', width: 92, ...style,
    }}>
      <Icon name={icon} size={30} strokeWidth={1.75} color="var(--ov-accent)" />
      <span style={{
        fontFamily: 'var(--ov-font-body)', fontWeight: 'var(--ov-w-semibold)',
        fontSize: 'var(--ov-text-xs)', color: 'var(--ov-text)', lineHeight: 1.25,
      }}>{label}</span>
    </div>
  );
}
```

### Metric

```tsx
// Metric.d.ts
import React from 'react';
export interface MetricProps {
  /** Lucide icon (battery, droplet, sun, zap, plug…) */
  icon: string;
  /** the reading, e.g. "78%" or "2.3 kW" */
  value: string;
  /** uppercase caption, e.g. "BATTERY" */
  label: string;
  /** render for placement on a dark status bar */
  onBar?: boolean;
  style?: React.CSSProperties;
}
export function Metric(props: MetricProps): JSX.Element;
```

```jsx
// Metric.jsx
import React from 'react';
import { Icon } from '../core/Icon.jsx';

/**
 * Metric — a single vitals readout (icon + value + uppercase label), as seen
 * in the persona status bar. `onBar` uses the status-bar text color.
 */
export function Metric({ icon, value, label, onBar = false, style = {} }) {
  const textColor = onBar ? 'var(--ov-statusbar-text)' : 'var(--ov-text)';
  const muted = onBar ? 'color-mix(in oklch, var(--ov-statusbar-text) 68%, transparent)' : 'var(--ov-text-muted)';
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3, ...style }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
        <Icon name={icon} size={18} color="var(--ov-accent)" strokeWidth={2} />
        <span style={{ fontFamily: 'var(--ov-font-mono)', fontWeight: 'var(--ov-w-bold)', fontSize: 'var(--ov-text-lg)', color: textColor, lineHeight: 1 }}>{value}</span>
      </div>
      <span style={{ fontFamily: 'var(--ov-font-body)', fontWeight: 'var(--ov-w-bold)', fontSize: 'var(--ov-text-2xs)', letterSpacing: '.1em', textTransform: 'uppercase', color: muted }}>{label}</span>
    </div>
  );
}
```

### PersonaTitle

```tsx
// PersonaTitle.d.ts
import React from 'react';
export interface PersonaTitleProps {
  /** the big name, e.g. "AURORA" */
  name: string;
  /** italic script tagline, e.g. "The Sunrise Chaser" */
  tagline?: string;
  /** CSS font-size for the name (tagline scales from it) */
  size?: string | number;
  style?: React.CSSProperties;
}
export function PersonaTitle(props: PersonaTitleProps): JSX.Element;
```

```jsx
// PersonaTitle.jsx
import React from 'react';

/**
 * PersonaTitle — the poster-scale persona name with its italic script tagline
 * ("AURORA" / "The Sunrise Chaser"). The signature OpenVan header element.
 */
export function PersonaTitle({ name, tagline, size = 'var(--ov-text-display)', style = {} }) {
  return (
    <div style={{ ...style }}>
      <h1 style={{
        margin: 0, fontFamily: 'var(--ov-font-display)', fontWeight: 'var(--ov-w-black)',
        fontSize: size, letterSpacing: 'var(--ov-track-display)', textTransform: 'uppercase',
        color: 'var(--ov-accent)', lineHeight: 0.92,
      }}>{name}</h1>
      {tagline && (
        <div style={{
          fontFamily: 'var(--ov-font-script)', fontWeight: 'var(--ov-w-bold)',
          fontSize: `calc(${typeof size === 'string' ? size : size + 'px'} * 0.42)`,
          color: 'var(--ov-tagline)', lineHeight: 1, marginTop: 4,
        }}>{tagline}</div>
      )}
    </div>
  );
}
```

### PersonalityTrait

```tsx
// PersonalityTrait.d.ts
import React from 'react';
export interface PersonalityTraitProps {
  /** Lucide icon in the circle */
  icon: string;
  /** accent-colored trait name */
  title: string;
  /** short description */
  children?: React.ReactNode;
  style?: React.CSSProperties;
}
export function PersonalityTrait(props: PersonalityTraitProps): JSX.Element;
```

```jsx
// PersonalityTrait.jsx
import React from 'react';
import { Icon } from '../core/Icon.jsx';

/**
 * PersonalityTrait — one row in the PERSONALITY list: a thin circular icon,
 * an accent title, and a short two-line description.
 */
export function PersonalityTrait({ icon, title, children, style = {} }) {
  return (
    <div style={{ display: 'flex', gap: 'var(--ov-space-4)', alignItems: 'flex-start', ...style }}>
      <span style={{
        flex: '0 0 46px', width: 46, height: 46, borderRadius: '999px',
        border: '1.5px solid var(--ov-accent)', display: 'inline-flex',
        alignItems: 'center', justifyContent: 'center', color: 'var(--ov-accent)', marginTop: 2,
      }}>
        <Icon name={icon} size={21} />
      </span>
      <div>
        <div style={{
          fontFamily: 'var(--ov-font-body)', fontWeight: 'var(--ov-w-bold)',
          fontSize: 'var(--ov-text-lg)', color: 'var(--ov-accent)', lineHeight: 1.2,
        }}>{title}</div>
        <div style={{
          fontFamily: 'var(--ov-font-body)', fontWeight: 'var(--ov-w-regular)',
          fontSize: 'var(--ov-text-sm)', color: 'var(--ov-text)', lineHeight: 1.4, marginTop: 2,
        }}>{children}</div>
      </div>
    </div>
  );
}
```

### ProfileAvatar

```tsx
// ProfileAvatar.d.ts
import React from 'react';
export interface ProfileAvatarProps {
  /** Lucide icon for the persona mark */
  icon?: string;
  /** diameter px */
  size?: number;
  /** ring (outline) · soft (tinted) · solid (filled) · onbar (for dark status bars) */
  variant?: 'ring' | 'soft' | 'solid' | 'onbar';
  style?: React.CSSProperties;
}
export function ProfileAvatar(props: ProfileAvatarProps): JSX.Element;
```

```jsx
// ProfileAvatar.jsx
import React from 'react';
import { Icon } from '../core/Icon.jsx';

/**
 * ProfileAvatar — the circular persona mark (Aurora=sparkles, Forge=wrench,
 * Nomad=globe, Pulse=zap, Ranger=compass, Scout=leaf). Themed circle + icon.
 */
export function ProfileAvatar({ icon = 'sparkles', size = 56, variant = 'ring', style = {} }) {
  const variants = {
    ring: { background: 'transparent', color: 'var(--ov-accent)', border: '2px solid var(--ov-accent)' },
    soft: { background: 'var(--ov-accent-soft)', color: 'var(--ov-accent)', border: '1px solid var(--ov-border)' },
    solid: { background: 'var(--ov-accent)', color: 'var(--ov-on-accent)', border: '2px solid transparent' },
    onbar: { background: 'transparent', color: 'var(--ov-statusbar-text)', border: '2px solid color-mix(in oklch, var(--ov-statusbar-text) 45%, transparent)' },
  }[variant];
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      width: size, height: size, flex: `0 0 ${size}px`, borderRadius: '999px', ...variants, ...style,
    }}>
      <Icon name={icon} size={size * 0.46} strokeWidth={2} />
    </span>
  );
}
```

### QuoteBubble

```tsx
// QuoteBubble.d.ts
import React from 'react';
export interface QuoteBubbleProps {
  children?: React.ReactNode;
  /** monospace voice (Pulse) */
  mono?: boolean;
  onPlay?: () => void;
  style?: React.CSSProperties;
}
export function QuoteBubble(props: QuoteBubbleProps): JSX.Element;
```

```jsx
// QuoteBubble.jsx
import React from 'react';
import { IconButton } from '../core/IconButton.jsx';

/**
 * QuoteBubble — a row in the "X SAYS" list: a round play button + an italic
 * quote in a soft capsule. `mono` matches Pulse's terminal voice.
 */
export function QuoteBubble({ children, mono = false, onPlay, style = {} }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--ov-space-3)', ...style }}>
      <IconButton icon="volume-2" variant="soft" size="sm" label="Play" onClick={onPlay} />
      <div style={{
        flex: 1, background: 'var(--ov-surface-2)', border: '1px solid var(--ov-border)',
        borderRadius: 'var(--ov-radius-pill)', padding: '9px 16px',
        fontFamily: mono ? 'var(--ov-font-mono)' : 'var(--ov-font-body)',
        fontStyle: mono ? 'normal' : 'italic', fontSize: mono ? 'var(--ov-text-sm)' : 'var(--ov-text-sm)',
        color: 'var(--ov-text)', lineHeight: 1.35,
      }}>
        {children}
      </div>
    </div>
  );
}
```

### SectionLabel

```tsx
// SectionLabel.d.ts
import React from 'react';
export interface SectionLabelProps {
  children?: React.ReactNode;
  /** show a hairline rule beneath the label */
  rule?: boolean;
  style?: React.CSSProperties;
}
export function SectionLabel(props: SectionLabelProps): JSX.Element;
```

```jsx
// SectionLabel.jsx
import React from 'react';

/**
 * SectionLabel — the small uppercase heading used on persona cards
 * ("PERSONALITY", "WHAT AURORA DOES BEST", "AURORA SAYS"). Heavy display
 * type in the accent color, optionally with a hairline rule beneath.
 */
export function SectionLabel({ children, rule = false, style = {} }) {
  return (
    <div style={{ ...style }}>
      <div style={{
        fontFamily: 'var(--ov-font-display)', fontWeight: 'var(--ov-w-heavy)',
        fontSize: 'var(--ov-text-sm)', letterSpacing: 'var(--ov-track-label)',
        textTransform: 'uppercase', color: 'var(--ov-accent)', lineHeight: 1.1,
      }}>
        {children}
      </div>
      {rule && <div style={{ height: 1, background: 'var(--ov-border)', marginTop: 'var(--ov-space-3)' }} />}
    </div>
  );
}
```

### SpeechBubble

```tsx
// SpeechBubble.d.ts
import React from 'react';
export interface SpeechBubbleProps {
  children?: React.ReactNode;
  /** accent (persona fill) · ink (dark) · paper (light) */
  tone?: 'accent' | 'ink' | 'paper';
  tail?: 'bottom-left' | 'bottom-right';
  /** use the monospace voice (Pulse) */
  mono?: boolean;
  style?: React.CSSProperties;
}
export function SpeechBubble(props: SpeechBubbleProps): JSX.Element;
```

```jsx
// SpeechBubble.jsx
import React from 'react';

/**
 * SpeechBubble — the van's spoken line, shown over the hero image.
 * Rounded bubble with a tail. `tone` sets the fill; `mono` switches to the
 * monospace voice (used by Pulse). Text renders italic like the cards.
 */
export function SpeechBubble({ children, tone = 'accent', tail = 'bottom-left', mono = false, style = {} }) {
  const tones = {
    accent: { background: 'var(--ov-accent)', color: 'var(--ov-on-accent)' },
    ink: { background: 'var(--ov-canvas)', color: 'var(--ov-paper-100)' },
    paper: { background: 'var(--ov-surface)', color: 'var(--ov-text)', border: '1px solid var(--ov-border)' },
  }[tone];
  const bg = tones.background;
  const tailPos = {
    'bottom-left': { left: 28, bottom: -11 },
    'bottom-right': { right: 28, bottom: -11 },
  }[tail];
  return (
    <div style={{ position: 'relative', display: 'inline-block', maxWidth: 300, ...style }}>
      <div style={{
        ...tones, borderRadius: 'var(--ov-radius-lg)', padding: '14px 18px',
        fontFamily: mono ? 'var(--ov-font-mono)' : 'var(--ov-font-body)',
        fontStyle: mono ? 'normal' : 'italic', fontWeight: 'var(--ov-w-semibold)',
        fontSize: mono ? 'var(--ov-text-sm)' : 'var(--ov-text-base)', lineHeight: 1.35,
        boxShadow: 'var(--ov-shadow-md)',
      }}>
        {children}
      </div>
      <div style={{
        position: 'absolute', width: 22, height: 22, background: bg,
        transform: 'rotate(45deg)', borderRadius: 4, ...tailPos,
        borderRight: tones.border, borderBottom: tones.border,
      }} />
    </div>
  );
}
```

### StatusBar

```tsx
// StatusBar.d.ts
import React from 'react';
export interface StatusBarMetric { icon: string; value: string; label: string; }
export interface StatusBarProps {
  /** persona mark icon */
  icon?: string;
  /** persona name, UPPERCASE (renders as "NAME HERE.") */
  name?: string;
  /** the greeting question */
  prompt?: string;
  /** vitals shown at right */
  metrics?: StatusBarMetric[];
  style?: React.CSSProperties;
}
export function StatusBar(props: StatusBarProps): JSX.Element;
```

```jsx
// StatusBar.jsx
import React from 'react';
import { ProfileAvatar } from './ProfileAvatar.jsx';
import { Metric } from './Metric.jsx';

/**
 * StatusBar — the persona's bottom bar: avatar + "NAME HERE." greeting + prompt,
 * then a divided row of vitals Metrics. Sits on the dark status-bar surface.
 */
export function StatusBar({ icon = 'sparkles', name = 'AURORA', prompt = 'Where shall we chase the beauty today?', metrics = [], style = {} }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 'var(--ov-space-5)',
      background: 'var(--ov-statusbar-bg)', color: 'var(--ov-statusbar-text)',
      borderRadius: 'var(--ov-radius-lg)', padding: '16px 22px', boxShadow: 'var(--ov-shadow-md)',
      ...style,
    }}>
      <ProfileAvatar icon={icon} variant="onbar" size={52} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
        <span style={{ fontFamily: 'var(--ov-font-display)', fontWeight: 'var(--ov-w-heavy)', fontSize: 'var(--ov-text-xl)', letterSpacing: '.01em', lineHeight: 1 }}>{name} HERE.</span>
        <span style={{ fontFamily: 'var(--ov-font-body)', fontSize: 'var(--ov-text-sm)', color: 'color-mix(in oklch, var(--ov-statusbar-text) 78%, transparent)', lineHeight: 1.3 }}>{prompt}</span>
      </div>
      {metrics.length > 0 && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 'var(--ov-space-6)', marginLeft: 'auto',
          paddingLeft: 'var(--ov-space-6)', borderLeft: '1px solid color-mix(in oklch, var(--ov-statusbar-text) 22%, transparent)',
        }}>
          {metrics.map((m, i) => <Metric key={i} icon={m.icon} value={m.value} label={m.label} onBar />)}
        </div>
      )}
    </div>
  );
}
```
