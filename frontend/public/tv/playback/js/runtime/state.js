/**
 * Pure playback-state decisions for the TV player.
 *
 * DOM/media elements stay in tick.js; this module only normalizes room items
 * and evaluates timing boundaries so those decisions can be tested without a
 * browser or an active audio element.
 */

/**
 * Whether a media element has reached the end of a meaningful duration.
 * Short/unknown durations are treated as not ended because they are commonly
 * transient metadata values while the browser is still loading a source.
 */
export function mediaEndedAt(currentTime, duration, margin = 1.5) {
  const dur = Number(duration);
  const time = Number(currentTime) || 0;
  const slack = Number(margin);
  if (!Number.isFinite(dur) || dur < 2) return false;
  if (!Number.isFinite(time) || !Number.isFinite(slack) || slack < 0) return false;
  return time >= dur - slack;
}

/** @param {QueueItem | null | undefined} item */
export function roomItemIdentity(item) {
  if (!item) return { itemKey: "", mediaRev: "" };
  return {
    itemKey: String(item.id || item.song_id || ""),
    mediaRev: String(item.media_rev || "")
  };
}

/**
 * Match the reload policy used by the TV player: a new queue item always
 * reloads, while a changed non-empty media revision reloads the same item.
 */
export function shouldReloadRoomItem(previousItemKey, previousMediaRev, item) {
  const next = roomItemIdentity(item);
  return (
    next.itemKey !== String(previousItemKey || "") ||
    (!!next.mediaRev && next.mediaRev !== String(previousMediaRev || ""))
  );
}
