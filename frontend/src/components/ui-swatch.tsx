/** Legend swatch: a short line segment in the series colour and dash pattern. */
import type { SeriesStyle } from "../lib/colors";

export function Swatch({ style }: { style: SeriesStyle }) {
  return (
    <svg width="18" height="8" className="shrink-0" aria-hidden>
      <line x1="1" y1="4" x2="17" y2="4" stroke={style.color} strokeWidth="2.5" strokeDasharray={style.dash} strokeLinecap="round" />
    </svg>
  );
}
