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
type LyricMode = "ja" | "zh" | "roma" | "all";
type LearnMode = "quiz" | "echo";
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
  lyric_mode?: LyricMode | string;
  detail?: string;
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

interface LearnLine {
  index: number;
  start_ms: number;
  end_ms: number;
  text: string;
  zh?: string;
  romaji?: string;
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
}

interface LearnEchoClip {
  start_ms: number;
  end_ms: number;
  blob: Blob | null;
}

interface LearnEchoSession {
  lines: LearnLine[];
  index: number;
  clips: LearnEchoClip[];
  mixUrl: string;
  running: boolean;
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
