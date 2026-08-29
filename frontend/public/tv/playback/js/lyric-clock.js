/** Karaoke audio is the master clock. Native MV and lyric paint follow it. */
export const SYNC_SLACK_MS = 800;
export const SEEK_COOLDOWN_MS = 2000;
export const CLOCK_WARMUP_MS = 200;

export function lyricOffsetMs(lyrics) {
  if (!lyrics) return 0;
  const raw = lyrics.offset_ms != null ? lyrics.offset_ms : lyrics.lyric_offset_ms;
  const n = Number(raw);
  return Number.isFinite(n) ? n : 0;
}

export function lyricClockMs(audioMs, lyrics) {
  const t = Math.round(Number(audioMs) || 0) + lyricOffsetMs(lyrics);
  return t < 0 ? 0 : t;
}

/** Official MV sometimes has a longer intro than karaoke. Extra 1.5–30s is treated as lead-in. */
export function videoLeadMs(mtvDurationMs, karaokeDurationMs) {
  const extra = Math.round((Number(mtvDurationMs) || 0) - (Number(karaokeDurationMs) || 0));
  if (extra >= 1500 && extra <= 30000) return extra;
  return 0;
}

export function videoSeekMs(audioMs, mtvDurationMs, karaokeDurationMs) {
  const t = Math.round(Number(audioMs) || 0) + videoLeadMs(mtvDurationMs, karaokeDurationMs);
  return t < 0 ? 0 : t;
}

export function shouldSeekNative(nativeMs, targetMs, lastSeekAt, now, playing) {
  if (playing === false) return false;
  const native = Number(nativeMs) || 0;
  const target = Number(targetMs) || 0;
  if (native < CLOCK_WARMUP_MS && target > 1000) return false;
  if (Math.abs(native - target) <= SYNC_SLACK_MS) return false;
  if ((Number(now) || 0) - (Number(lastSeekAt) || 0) < SEEK_COOLDOWN_MS) return false;
  return true;
}
