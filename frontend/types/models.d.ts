type SongStatus = "queued" | "fetching" | "separating" | "aligning" | "annotating" | "composing" | "ready" | "failed";

type PhonePage = "search" | "desk" | "player";
type PlayOrder = "seq" | "shuffle";
type LyricMode = "ja" | "zh" | "roma" | "all";
type RoomAction = "enqueue" | "bump" | "skip" | "play" | "mix";
type LearnMode = "quiz" | "tap" | "echo";
type LearnQuestionKind = "meaning" | "word" | "listen";

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
  song_id?: string;
  title: string;
  artist?: string;
  language?: string;
  status: SongStatus | string;
  error?: string;
  native_video?: boolean;
  media_rev?: string;
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
  lyric_mode?: LyricMode | string;
  paused?: boolean | number;
  lan_origin?: string;
  lan_mic_port?: number;
  lan_mic_sample_rate?: number;
  lan_seen_at?: number;
  detail?: string;
}

interface RoomCommand {
  action: RoomAction;
  id?: string;
  item_id?: string;
  song_id?: string;
  vocal_mix?: number;
  volume?: number;
  mic_gain?: number;
  lyric_mode?: LyricMode | string;
  paused?: boolean | number | string;
}

interface LyricToken {
  text: string;
  start_ms: number;
  end_ms: number;
  reading?: string;
  romaji?: string;
  zh?: string;
}

interface LyricCue {
  text: string;
  start_ms: number;
  end_ms: number;
  tokens?: LyricToken[];
  zh?: string;
  romaji?: string;
  source_text?: string;
}

interface LyricsDoc {
  cues: LyricCue[];
  native_video?: boolean;
  language?: string;
  alignment?: string;
  alignment_source?: string;
  duration_ms?: number;
}

interface MtvSkeleton {
  has_video?: boolean;
}

interface AuthUser {
  id?: string;
  sid?: string;
  nickname?: string;
  avatar?: string;
  wechat?: boolean;
  username?: string;
  account?: boolean;
}

interface AuthQuota {
  unlimited?: boolean;
  limit?: number;
  used?: number;
  remaining?: number | null;
  account?: boolean;
}

interface PointsState {
  balance?: number;
  queue_cost?: number;
  process_cost?: number;
  ad_reward?: number;
  ad_seconds?: number;
  register_bonus?: number;
  download_bonus?: number;
}

interface SongListPage {
  songs?: Song[];
  page?: number;
  pages?: number;
  total?: number;
  lib_total?: number;
  after?: string;
  letters?: string[];
}

interface SearchPage {
  hits?: SearchHit[];
  has_more?: boolean;
  detail?: string;
  page?: number;
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

interface LearnChoice {
  id: number;
  text: string;
}

interface LearnQuestion {
  id: string;
  kind: LearnQuestionKind | string;
  prompt: string;
  stem: string;
  choices: LearnChoice[];
  answer: number;
}

interface LearnWord {
  text: string;
  romaji?: string;
  zh?: string;
}

interface LearnLine {
  index: number;
  start_ms: number;
  end_ms: number;
  text: string;
  zh?: string;
  romaji?: string;
  words?: LearnWord[];
  questions: LearnQuestion[];
}

interface LearnQuiz {
  schema?: string;
  song_id: string;
  title?: string;
  artist?: string;
  language?: string;
  modes?: LearnMode[];
  questions_per_line?: number;
  lines: LearnLine[];
  total_questions: number;
}

interface LearnSession {
  quiz: LearnQuiz | null;
  line: number;
  answers: Record<string, number>;
  jump?: number;
}

interface LearnEchoClip {
  start_ms: number;
  end_ms: number;
  rec_end_ms: number;
  blob: Blob | null;
}

interface LearnEchoSession {
  lines: LearnLine[];
  index: number;
  clips: LearnEchoClip[];
  mixUrl: string;
  running: boolean;
  review: ((action: LearnEchoReview) => void) | null;
  previewUrl: string;
  skipped: boolean;
}

type LearnEchoReview = "next" | "retry" | "skip" | "stop";

interface LearnScoreView {
  title: string;
  again: string;
  sub: string;
  detail: string;
  mixUrl?: string;
  celebrate?: boolean;
}

interface LearnTapSession {
  lines: LearnLine[];
  index: number;
  cursor: number;
  running: boolean;
  hits: number;
  misses: number;
  combo: number;
  maxCombo: number;
  perfect: number;
  lineMisses: number;
  jump?: number;
}

interface LearnFxDot {
  x: number;
  y: number;
  vx: number;
  vy: number;
  life: number;
  decay: number;
  r: number;
  color: string;
  star: boolean;
}

interface LearnFxRing {
  x: number;
  y: number;
  r: number;
  grow: number;
  life: number;
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
  learn: string;
}
