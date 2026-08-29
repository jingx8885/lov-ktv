/**
 * Pure player-state transitions. Audio elements and DOM remain in playback.js;
 * this module only decides the next catalog item, which keeps playback policy
 * testable without a browser.
 */
export function nextSongId(catalog, currentId, order, random = Math.random) {
  const ids = (catalog || []).map((song) => song && song.id).filter(Boolean);
  if (!ids.length) return "";
  if (order === "shuffle") {
    const pool = ids.filter((id) => id !== currentId);
    const src = pool.length ? pool : ids;
    return src[Math.floor(random() * src.length)];
  }
  const index = Math.max(0, ids.indexOf(currentId));
  return ids[(index + 1) % ids.length];
}
