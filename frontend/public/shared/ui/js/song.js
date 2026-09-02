/**
 * Catalog titles imported from providers are stored as "Title · Artist".
 * Mirrors backend `catalog.index.display_title` / `display_artist` so list
 * rows never repeat the artist on two lines.
 */
const SEP = " · ";

export function songTitle(song) {
  const title = String((song && song.title) || "").trim();
  const at = title.indexOf(SEP);
  return at > 0 ? title.slice(0, at).trim() : title;
}

export function songArtist(song) {
  const artist = String((song && song.artist) || "").trim();
  if (artist) return artist;
  const title = String((song && song.title) || "");
  const at = title.indexOf(SEP);
  return at > 0 ? title.slice(at + SEP.length).trim() : "";
}
