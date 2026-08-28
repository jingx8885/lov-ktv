type SongStatus =
  | "queued"
  | "fetching"
  | "separating"
  | "aligning"
  | "annotating"
  | "composing"
  | "ready"
  | "failed";

type PhonePage = "search" | "desk" | "player";
type PlayOrder = "seq" | "shuffle";

interface SearchHit {
  id: string;
  title: string;
  artist?: string;
  language?: string;
  source?: string;
  is_mv?: boolean;
}

interface Song {
  id: string;
  title: string;
  artist?: string;
  language?: string;
  status: SongStatus | string;
  error?: string;
  native_video?: boolean;
  letter?: string;
}

interface QueueItem extends Song {
  song_id: string;
  position?: number;
}

interface Room {
  code: string;
  queue: QueueItem[];
  now_playing?: QueueItem | null;
  now_index: number;
  vocal_mix?: number;
  volume?: number;
  mic_gain?: number;
  mic_on?: boolean;
  host_volume_kind?: string;
  detail?: string;
}

interface LyricToken {
  text: string;
  start_ms: number;
  end_ms: number;
  reading?: string;
  romaji?: string;
}

interface LyricCue {
  text: string;
  start_ms: number;
  end_ms: number;
  tokens?: LyricToken[];
}

interface LyricsDoc {
  cues: LyricCue[];
  native_video?: boolean;
}

interface MtvSkeleton {
  has_video?: boolean;
}

interface AuthUser {
  sid?: string;
  nickname?: string;
  avatar?: string;
  wechat?: boolean;
}

interface SongListPage {
  songs?: Song[];
  page?: number;
  pages?: number;
  total?: number;
  lib_total?: number;
  letters?: string[];
}

interface SearchPage {
  hits?: SearchHit[];
  has_more?: boolean;
  detail?: string;
}

interface PhoneLibState {
  q: string;
  by: string;
  letter: string;
  page: number;
}

interface LyricPaintSlots {
  prev: string;
  cur: string;
  next: string;
  align?: string;
}

interface ActionSheetOpts {
  title?: string;
  message?: string;
  confirm?: string;
  danger?: boolean;
}

interface LoadPlayerOpts {
  play?: boolean;
}

interface PhoneIcons {
  play: string;
  pause: string;
  listen: string;
  plus: string;
  trash: string;
  save: string;
  seq: string;
  shuffle: string;
}
