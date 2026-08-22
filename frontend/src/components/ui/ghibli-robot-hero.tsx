"use client";

import {
  useEffect,
  type AnchorHTMLAttributes,
  type CSSProperties,
  type ReactNode,
} from "react";
import { cn } from "@/lib/utils";

/* --- Fonts --- */

/**
 * The two faces this hero is drawn in. Averia Serif Libre carries the
 * headline; General Sans carries everything else.
 *
 * They load from a stylesheet link rather than a bundler import so the file
 * stays self-contained — drop it in and it looks right, with no font wiring in
 * the host app. If your app already ships these faces, pass `loadFonts={false}`
 * and the component uses whatever you have.
 */
const FONT_HREFS = [
  "https://fonts.googleapis.com/css2?family=Averia+Serif+Libre:wght@300;400;700&display=swap",
  "https://api.fontshare.com/v2/css?f[]=general-sans@300,400,500,600&display=swap",
];

const SERIF = "'Averia Serif Libre', ui-serif, Georgia, Cambria, serif";
const SANS =
  "'General Sans', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif";

/** Adds each font stylesheet to the head once, however many heroes are mounted. */
function useWebFonts(enabled: boolean) {
  useEffect(() => {
    if (!enabled || typeof document === "undefined") return;
    for (const href of FONT_HREFS) {
      if (document.querySelector(`link[href="${href}"]`)) continue;
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = href;
      document.head.appendChild(link);
    }
  }, [enabled]);
}

/* --- Motion --- */

/**
 * The copy rises into place on load. Behind a reduced-motion guard, so a reader
 * who asks for stillness gets a still page.
 */
const HERO_STYLES = `
@keyframes ghibli-robot-hero-rise {
  from { opacity: 0; transform: translateY(16px); }
  to   { opacity: 1; transform: none; }
}
@media (prefers-reduced-motion: reduce) {
  .ghibli-robot-hero-rise { animation: none !important; opacity: 1 !important; transform: none !important; }
}
`;

/**
 * What the button does under the pointer.
 *
 * The sheen has to be driven from `:hover` rather than left looping under a
 * fading mask: a loop is wherever it happens to be when the pointer arrives, so
 * half the time you catch it parked at the far edge and the button just glows.
 * Tied to hover it starts off the left edge every time and crosses once.
 *
 * The face also lifts, the way it does on cluely.com — a wash of white blended
 * with `overlay`, faded in over the paint rather than added to it.
 */
const BUTTON_STYLES = `
@keyframes ghibli-robot-hero-sheen {
  from { transform: translateX(-140%) skewX(-16deg); }
  to   { transform: translateX(320%)  skewX(-16deg); }
}
.ghibli-robot-hero-sheen { transform: translateX(-140%) skewX(-16deg); }
.ghibli-robot-hero-btn:hover .ghibli-robot-hero-sheen {
  animation: ghibli-robot-hero-sheen 0.85s cubic-bezier(0.32, 0, 0.24, 1);
}
.ghibli-robot-hero-btn::after {
  content: "";
  position: absolute;
  inset: 1px;
  z-index: 1;
  border-radius: inherit;
  opacity: 0;
  mix-blend-mode: overlay;
  background: radial-gradient(101.79% 101.79% at 65.61% 81.79%, rgba(255,255,255,0.6) 0%, rgba(255,255,255,0) 100%);
  transition: opacity 0.3s ease-in-out;
}
.ghibli-robot-hero-btn:hover::after { opacity: 1; }
@media (prefers-reduced-motion: reduce) {
  .ghibli-robot-hero-btn:hover .ghibli-robot-hero-sheen { animation: none; }
}
`;

/** One rising line. `step` orders it against its neighbours. */
function rise(step: number): CSSProperties {
  return {
    animation: `ghibli-robot-hero-rise 0.7s cubic-bezier(0.22, 1, 0.36, 1) ${step * 0.09}s both`,
  };
}

/* --- Button --- */

/**
 * The blue pill from cluely.com, rebuilt from its computed styles.
 *
 * Four layers make the glass:
 *
 * 1. Two stacked radial gradients — a wash of white low and right, over a blue
 *    that runs from sky to ink — blended with `overlay`, which is what stops it
 *    reading as flat paint.
 * 2. A hairline that is bright at the top and gone by the bottom. It is drawn
 *    as a padded box masked down to its own edge, because a plain border cannot
 *    take a gradient.
 * 3. Two inset shadows: cold light on the top-left lip, deep blue in the
 *    bottom-right well.
 * 4. A narrow band of light that crosses the face once per hover, over a wash
 *    that lifts the whole face while the pointer is on it. See `BUTTON_STYLES`.
 */
export interface GhibliRobotHeroButtonProps
  extends AnchorHTMLAttributes<HTMLAnchorElement> {
  /** Icon drawn to the left of the label. */
  icon?: ReactNode;
  children?: ReactNode;
}

export function GhibliRobotHeroButton({
  icon,
  children,
  className,
  style,
  ...rest
}: GhibliRobotHeroButtonProps) {
  return (
    <a
      {...rest}
      className={cn(
        "ghibli-robot-hero-btn relative inline-flex w-fit items-center gap-[6px] overflow-hidden rounded-[10px]",
        "px-5 py-[10px] text-[16px] font-medium tracking-[-0.13px] text-white",
        "transition-transform duration-150 ease-out active:scale-[0.97]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70 focus-visible:ring-offset-2 focus-visible:ring-offset-transparent",
        className,
      )}
      style={{
        fontFamily: SANS,
        backgroundImage:
          "radial-gradient(101.79% 101.79% at 65.61% 81.79%, rgba(255,255,255,0.6) 0%, rgba(255,255,255,0) 100%), radial-gradient(114.65% 114.65% at 9.73% 17.27%, #1e82e0 0%, #1c38ea 100%)",
        backgroundBlendMode: "overlay, normal",
        boxShadow:
          "20px 20px 24px rgba(148,172,243,0.4), inset -3px -3px 4px rgba(191,229,251,0.4), inset 4px 4px 4px rgba(19,26,228,0.1)",
        ...style,
      }}
    >
      <style>{BUTTON_STYLES}</style>

      {/* The lit edge. Blurred by a hair so it reads as glass, not as a stroke. */}
      <span
        aria-hidden
        className="pointer-events-none absolute inset-0 z-20 blur-[1px]"
      >
        <span
          className="absolute -left-px -top-px z-20 h-full w-full"
          style={{
            opacity: 0.45,
            padding: 3,
            borderRadius: 10,
            background:
              "linear-gradient(176.87deg, rgba(255,255,255,0.5) 8.56%, rgba(255,255,255,0) 85.04%)",
            WebkitMask:
              "linear-gradient(#fff, #fff) content-box, linear-gradient(#fff, #fff)",
            WebkitMaskComposite: "xor",
            mask: "linear-gradient(#fff, #fff) content-box, linear-gradient(#fff, #fff)",
            maskComposite: "exclude",
          }}
        />
      </span>

      {/* The sweep. It waits off the left edge and crosses once per hover. */}
      <span
        aria-hidden
        className="ghibli-robot-hero-sheen pointer-events-none absolute inset-y-0 left-0 z-10 w-1/3 blur-[5px]"
        style={{
          background:
            "linear-gradient(90deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.55) 50%, rgba(255,255,255,0) 100%)",
        }}
      />

      {icon ? <span className="relative z-30 -mb-px">{icon}</span> : null}
      <span className="relative z-30">{children}</span>
    </a>
  );
}

/* --- Types --- */

export interface GhibliRobotHeroProps {
  /**
   * The background picture, and the fallback for browsers that skip `sources`.
   * Give it the largest copy you have.
   *
   * A hero this tall crops a landscape hard: the section takes the full height
   * of the screen, so the browser scales the picture until its short side fits
   * and throws the rest away sideways. That means the file wants to be tall,
   * not merely wide — 1500px down the short side before it starts to soften on
   * a retina screen.
   */
  image?: string;
  /**
   * Smaller copies of the same picture with their widths, so a phone is not
   * made to fetch the desktop file. Passed straight to `srcset`.
   */
  sources?: Array<{ src: string; width: number }>;
  /**
   * What width to tell the browser to shop for in `sources`.
   *
   * The obvious `100vw` is wrong here and gives a soft picture. It measures the
   * width of the box, but a full-height cover crop is decided by the height:
   * the browser scales until the short side fits and spills the rest sideways,
   * so the file it needs is as wide as the screen is *tall*, times the aspect
   * of the picture. The default asks for whichever of the two is larger, at
   * about 16:9. Pass `"100vw"` to favour bytes over detail.
   */
  sizes?: string;
  /** Alt text for the picture. Leave empty when it is pure decoration. */
  imageAlt?: string;
  /**
   * Which part of the picture stays in frame as the section is cropped, given
   * as a CSS `object-position`.
   */
  focus?: string;
  /** Small line above the headline. */
  eyebrow?: ReactNode;
  /** The headline. Set in Averia Serif Libre. */
  title: ReactNode;
  /** One or two lines under the headline. */
  subtitle?: ReactNode;
  /** Text on the button. Leave unset to drop the button. */
  ctaLabel?: string;
  /** Where the button points. */
  ctaHref?: string;
  /** Icon inside the button, to the left of the label. */
  ctaIcon?: ReactNode;
  /** Quiet line under the button — a price, a platform, a promise. */
  note?: ReactNode;
  /**
   * How hard the picture is darkened behind the copy, from 0 to 1. The default
   * of 0.85 keeps the meadow bright and only weighs down the sky.
   */
  scrim?: number;
  /** How far down the section the copy sits, from 0 (top) to 1 (bottom). */
  lead?: number;
  /**
   * Height of the section. Any CSS length. The default fills the screen, so
   * the picture runs to the bottom edge with no strip of page showing under it.
   */
  minHeight?: string;
  /** Load Averia Serif Libre and General Sans from the web. */
  loadFonts?: boolean;
  /** Replaces the button and the note under it. */
  children?: ReactNode;
  className?: string;
}

/* --- Component --- */

/**
 * A hero that sits inside its picture rather than on top of it.
 *
 * The problem with white type on a bright photograph is that a flat black
 * overlay fixes the reading and ruins the picture. So the veil here is a
 * gradient: heavy across the sky, where the words are, and gone by the middle
 * of the frame, where the land begins. A soft pool of shade sits behind the
 * copy itself for the same reason — it follows the text instead of the frame.
 *
 * The headline is a serif and everything around it is a grotesque, so the two
 * never compete. Both faces load themselves; see `loadFonts`.
 */
export function GhibliRobotHero({
  image = "/ghibli-robot-hero-5504.webp",
  sources,
  sizes = "max(100vw, 180svh)",
  imageAlt = "",
  focus = "50% 62%",
  eyebrow,
  title,
  subtitle,
  ctaLabel,
  ctaHref = "#",
  ctaIcon,
  note,
  scrim = 0.85,
  lead = 0.34,
  minHeight = "100svh",
  loadFonts = true,
  children,
  className,
}: GhibliRobotHeroProps) {
  useWebFonts(loadFonts);

  const veil = Math.max(0, Math.min(1, scrim));

  return (
    <section
      className={cn(
        "relative isolate w-full overflow-hidden bg-[#0d2440]",
        className,
      )}
      style={{ minHeight, fontFamily: SANS }}
    >
      <style>{HERO_STYLES}</style>

      {/* Picture, then the two veils, then the copy — stacked by explicit z
          rather than by a negative index on the picture, so a background set on
          the section from outside cannot land in the middle of the pile. */}
      <img
        src={image}
        srcSet={
          sources?.length
            ? sources.map((s) => `${s.src} ${s.width}w`).join(", ")
            : undefined
        }
        sizes={sources?.length ? sizes : undefined}
        alt={imageAlt}
        aria-hidden={imageAlt ? undefined : true}
        decoding="async"
        className="absolute inset-0 z-0 h-full w-full object-cover"
        style={{ objectPosition: focus }}
      />

      {/* At scrim 0 the picture is left alone and the text carries itself on
          its own shadow, so neither veil is drawn at all. */}
      {veil > 0 ? (
        <>
          {/* Weight across the reading band, and none at the top edge — a veil
              that starts at full strength turns a blue sky grey. */}
          <div
            aria-hidden
            className="absolute inset-0 z-0"
            style={{
              background: `linear-gradient(to bottom,
                rgba(5,18,40,${0.14 * veil}) 0%,
                rgba(5,18,40,${0.3 * veil}) 30%,
                rgba(5,18,40,${0.12 * veil}) 58%,
                rgba(5,18,40,0) 74%)`,
            }}
          />

          {/* Shade that follows the words rather than the frame. It is tall
              enough to reach the line under the button, which otherwise lands
              on cloud. */}
          <div
            aria-hidden
            className="absolute inset-0 z-0"
            style={{
              background: `radial-gradient(56% 54% at 50% ${lead * 100 + 12}%,
                rgba(3,14,32,${0.46 * veil}) 0%,
                rgba(3,14,32,${0.26 * veil}) 48%,
                rgba(3,14,32,0) 78%)`,
            }}
          />
        </>
      ) : null}

      <div
        className="relative z-10 flex h-full w-full flex-col items-center px-6 text-center sm:px-10"
        style={{
          minHeight,
          paddingTop: `calc(${lead} * ${minHeight} - 6rem)`,
          paddingBottom: "4rem",
        }}
      >
        {eyebrow ? (
          <p
            className="ghibli-robot-hero-rise mb-5 text-[13px] font-medium uppercase tracking-[0.18em] text-white/70"
            style={rise(0)}
          >
            {eyebrow}
          </p>
        ) : null}

        <h1
          className="ghibli-robot-hero-rise max-w-[20ch] text-balance text-[clamp(2.5rem,7.4vw,5rem)] font-normal leading-[1.02] tracking-[-0.02em] text-white"
          style={{
            ...rise(1),
            fontFamily: SERIF,
            textShadow: "0 2px 30px rgba(3,16,38,0.4)",
          }}
        >
          {title}
        </h1>

        {subtitle ? (
          <p
            className="ghibli-robot-hero-rise mt-6 max-w-[86ch] text-pretty text-[clamp(1rem,1.5vw,1.175rem)] font-normal leading-relaxed text-white"
            style={{
              ...rise(2),
              textShadow: "0 1px 18px rgba(3,16,38,0.45)",
            }}
          >
            {subtitle}
          </p>
        ) : null}

        <div
          className="ghibli-robot-hero-rise mt-9 flex flex-col items-center gap-3"
          style={rise(3)}
        >
          {children ??
            (ctaLabel ? (
              <GhibliRobotHeroButton href={ctaHref} icon={ctaIcon}>
                {ctaLabel}
              </GhibliRobotHeroButton>
            ) : null)}

          {note ? (
            <p
              className="text-[13px] text-white/70"
              style={{ textShadow: "0 1px 10px rgba(3,16,38,0.9)" }}
            >
              {note}
            </p>
          ) : null}
        </div>
      </div>
    </section>
  );
}

export default GhibliRobotHero;
