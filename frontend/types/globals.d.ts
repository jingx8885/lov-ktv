interface BandsHook {
  audio?: HTMLMediaElement;
  ctx?: AudioContext;
  analyser?: AnalyserNode;
  freq?: Uint8Array;
  time?: Uint8Array;
  source?: MediaElementAudioSourceNode;
  gain?: GainNode;
}

interface BandsDrawFrame {
  playing?: boolean;
  freq?: Uint8Array | null;
  wave?: Uint8Array | null;
  playMs?: number;
  duration?: number;
  cues?: LyricCue[];
  selected?: number;
}

interface BandsViz {
  draw(frame?: BandsDrawFrame | BandsHook): void;
  resize?: () => void;
  setSource(url: string): void;
}

interface LovBandsApi {
  create(el: HTMLElement | null): BandsViz;
  hookAnalyser(
    audio: HTMLMediaElement | null,
    prev?: BandsHook | null,
    opts?: { ctx?: AudioContext; latencyHint?: string }
  ): BandsHook | null;
  pull(hooked?: BandsHook | null): Uint8Array | null;
  getOverview(url: string): Float32Array | null;
  decodeOverview(url: string): Promise<Float32Array>;
}

interface LovMicMsg {
  event?: string;
  role?: string;
  kind?: string;
  [key: string]: unknown;
}

interface LovMicHandlers {
  onOpen?: () => void;
  onSnapshot?: (room: Room) => void;
  onPeer?: (msg: LovMicMsg) => void;
  onRtc?: (msg: LovMicMsg) => void;
  onError?: (msg: LovMicMsg) => void;
  onState?: (state: string) => void;
  onStream?: (stream: MediaStream) => void;
}

interface LovMicSession {
  native?: boolean;
  peerId: string;
  connect(roomCode: string, handlers?: LovMicHandlers): void;
  disconnect(): void;
  send(msg: unknown): void;
  startMic(opts?: unknown): Promise<unknown>;
  stopMic(): Promise<void>;
  makeOffer(): Promise<unknown>;
  handleAnswer(msg: unknown): Promise<unknown>;
  handleOffer(msg: unknown): Promise<unknown>;
  addIce(msg: unknown): Promise<unknown>;
  resetPc(): Promise<unknown>;
  isLive(): boolean;
}

interface LovMicApi {
  create(opts?: { role?: string; peerId?: string }): LovMicSession;
  micErrorText(err: unknown): string;
}

interface LovAecAttachOpts {
  gain?: number;
  karaoke?: HTMLMediaElement;
  vocal?: HTMLMediaElement;
  hook?: BandsHook | null;
}

interface LovAecApi {
  ensureCtx(): Promise<AudioContext | null>;
  getCtx(): AudioContext | null;
  attach(stream: MediaStream, opts?: LovAecAttachOpts): Promise<boolean> | boolean;
  detach(): void;
  retap(hook?: BandsHook | null): void;
  setGain(value: number): void;
  isActive(): boolean;
}

interface LovTimelineHandle {
  render(): void;
  sync(ms: number, dur?: number): void;
  zoom(dir: number): void;
  setChain(on: boolean): void;
  setVoiceUrl(url: string): void;
  setVoiceOn(on: boolean): void;
  setMixOn(on: boolean): void;
  seek(ms: number): void;
  isDragging(): boolean;
}

interface LovTimelineOpts {
  root: HTMLElement;
  stage: HTMLElement;
  wave?: HTMLCanvasElement;
  voice?: HTMLCanvasElement | null;
  ruler?: HTMLElement;
  track?: HTMLElement;
  getCues: () => LyricCue[];
  getAudio: () => HTMLMediaElement | null;
  selected?: () => number;
  onSeek?: (ms: number) => void;
  onSelect?: (index: number) => void;
  onGrab?: () => void;
  onReleaseCue?: (cue: LyricCue) => void;
  onChange?: () => void;
}

interface LovTimelineApi {
  create(opts: LovTimelineOpts): LovTimelineHandle;
}

interface StageFxDrawFrame {
  beat?: number;
  now?: number;
}

interface StageFxHandle {
  spawn(name?: string, cue?: LyricCue): void;
  draw(frame?: StageFxDrawFrame): void;
  clear(): void;
  resize?: () => void;
  setBeat?: (p: number) => void;
}

/** Internal stage-effect module contracts. These globals are installed by the
 * ordered scripts in tv.html. */
interface LovStageFxPrimitivesApi {
  EFFECTS: readonly string[];
  C: { amber: string; gray: string; ink: string };
  ACCENTS: readonly string[];
  FX_IN: number;
  FX_OUT: number;
  MAX_LAYERS: number;
  mulberry32(seed: number): () => number;
  clamp01(value: number): number;
  smooth(value: number): number;
  easeOutCubic(value: number): number;
  easeOutBack(value: number): number;
  easeOutElastic(value: number): number;
  prog(t: number, delay: number, duration?: number): number;
  pickColor(rng: () => number): string;
  tracePoly(ctx: CanvasRenderingContext2D, x: number, y: number, radius: number, sides: number, rotation: number): void;
  traceStar(
    ctx: CanvasRenderingContext2D,
    x: number,
    y: number,
    radius: number,
    points: number,
    rotation: number
  ): void;
  drawPiece(
    ctx: CanvasRenderingContext2D,
    kind: string,
    color: string,
    x: number,
    y: number,
    radius: number,
    rotation: number
  ): void;
  strokePartial(
    ctx: CanvasRenderingContext2D,
    points: Array<{ x: number; y: number }>,
    lengths: number[],
    visible: number
  ): { x: number; y: number };
}

interface LovStageFxBuildApi {
  [name: string]: (instance: any, rng: () => number, width: number, height: number) => void;
}

interface LovStageFxDrawApi {
  [name: string]: (
    ctx: CanvasRenderingContext2D,
    instance: any,
    t: number,
    fade: number,
    beat: number,
    width: number,
    height: number
  ) => void;
}

interface LovStageFxRuntimeApi {
  create(canvas: HTMLCanvasElement): StageFxHandle;
  reduceMotion(): boolean;
}

interface LovStageFxPartyApi {
  bind(canvas: HTMLElement | null): unknown;
  celebrate(kind?: string): void;
}

interface LovStageFxTextHooksApi {
  hookTexts(cues?: LyricCue[] | null): Set<string>;
}

interface KeepAliveTone {
  osc: OscillatorNode;
  gain: GainNode;
}

interface LovKtvRemoteApi {
  skip(): void | Promise<void>;
  toggleVocal(): void | Promise<void>;
  volumeUp(): void | Promise<void>;
  volumeDown(): void | Promise<void>;
  confirm(): void;
  start(): void | boolean;
  togglePaused?: () => void | Promise<void>;
  settings?: () => void | boolean;
  back?: () => void | boolean;
  __ready?: boolean;
  __module?: boolean;
}

interface LovI18nApi {
  LOCALES: readonly string[];
  t(key: string, vars?: Record<string, string | number>): string;
  lang(): string;
  setLang(next: string): string;
  applyDom(root?: ParentNode): void;
  bindLangPicker(root?: ParentNode): void;
  onLangChange(fn: (lang: string) => void): () => boolean;
  acceptLanguage(): string;
  parseLang(raw: string): string;
  bootI18n(): string;
}

interface HttpPort {
  available(): boolean;
  isLan(url: string): boolean;
  fetchJson(url: string, opts?: RequestInit): Promise<any> | null;
}

interface MediaPort {
  url(path: string): string;
}
interface MicPort {
  hasNative(): boolean;
  capabilities(): Record<string, unknown>;
  state(): Record<string, unknown>;
  call(method: string): Promise<string>;
  setGain(value: number): void;
}
interface RemotePort {
  open(url: string): boolean;
}
interface ScannerPort {
  available(): boolean;
  scan(): boolean;
  useLan(lan: string, room: string): boolean;
}

interface PhonePlatform {
  mic: MicPort;
  scanner: ScannerPort;
  media: MediaPort;
  remote: RemotePort;
  http: HttpPort;
  __onHttp?: (msg: any) => void;
}

interface PhoneMountDeps {
  api?: Partial<PhoneApi>;
  platform?: PhonePlatform;
}

interface TvPlatform {
  http: { available(): boolean; fetchJson: null };
  media: { url(path: string): string };
  mic: { available(): boolean };
  remote: { available(): boolean };
  scanner: { available(): boolean };
}

interface TvMountDeps {
  api?: Partial<TvApi>;
  platform?: TvPlatform;
}

type Platform = PhonePlatform | TvPlatform;

interface LovKtvNativeBridge {
  playMtv?: (url: string) => void;
  stopMtv?: () => void;
  pauseMtv?: () => void;
  resumeMtv?: () => void;
  durationMs?: () => number;
  positionMs?: () => number;
  playing?: () => boolean;
  seekMtv?: (positionMs: number) => void;
  openSetup?: () => void;
  startTvMic?: () => void;
  stopTvMic?: () => void;
  startIem?: () => void;
  stopIem?: () => void;
  capabilities?: () => string;
  state?: () => string;
  setGain?: (value: number) => void;
}

interface LovKtvPhoneBridge {
  version?: () => string;
  scanTv?: () => void;
  http?: (id: string, url: string, method: string, body: string) => void;
  useLan?: (lan: string, room: string) => void;
  capabilities?: () => string;
  state?: () => string;
  startTvMic?: () => string;
  stopTvMic?: () => string;
  startIem?: () => string;
  stopIem?: () => string;
  setGain?: (value: number) => void;
  openUrl?: (url: string) => void;
}

interface Window {
  LovI18n?: { acceptLanguage?: () => string };
  webkitAudioContext?: typeof AudioContext;
  webkitOfflineAudioContext?: typeof OfflineAudioContext;
  LovBands?: LovBandsApi;
  LovMic?: LovMicApi;
  LovAec?: LovAecApi;
  LovTimeline?: LovTimelineApi;
  LovStageFxPrimitives?: LovStageFxPrimitivesApi;
  LovStageFxBuild?: LovStageFxBuildApi;
  LovStageFxDraw?: LovStageFxDrawApi;
  LovStageFxRuntime?: LovStageFxRuntimeApi;
  LovStageFxParty?: LovStageFxPartyApi;
  LovStageFxTextHooks?: LovStageFxTextHooksApi;
  LovKtvRemote?: LovKtvRemoteApi;
  LovKtvPhone?: LovKtvPhoneBridge;
  LovI18n?: LovI18nApi;
  LovKtvPlatform?: PhonePlatform;
  LovKtvNative?: LovKtvNativeBridge;
  LovKtvOnHttp?: (msg: { id?: string; ok?: boolean; status?: number; body?: unknown }) => void;
  LovKtvOnMic?: ((ok: boolean, err?: string) => void) | null;
  __lovktvLanFetch?: boolean;
  __lovktvPlayBooted?: boolean;
  __lovktvQrBooted?: boolean;
  confetti?: { create?: (canvas: HTMLElement, opts?: object) => unknown };
}

declare const LovBands: LovBandsApi;
declare const LovMic: LovMicApi;
declare const LovAec: LovAecApi;
declare const LovTimeline: LovTimelineApi;
declare const LovStageFxRuntime: LovStageFxRuntimeApi;
declare const LovStageFxParty: LovStageFxPartyApi;
declare const LovStageFxTextHooks: LovStageFxTextHooksApi;

declare function qrcode(
  typeNumber: number,
  errorCorrectionLevel: string
): {
  addData(data: string): void;
  make(): void;
  createSvgTag(cellSize?: number, margin?: number): string;
  createImgTag?(cellSize?: number, margin?: number): string;
  getModuleCount?(): number;
  isDark?(row: number, col: number): boolean;
};

interface Element {
  onclick: ((this: GlobalEventHandlers, ev: MouseEvent) => any) | null;
  dataset: DOMStringMap;
  style: CSSStyleDeclaration;
  disabled: boolean;
  hidden: boolean;
  value: string;
  blur?: () => void;
}

interface HTMLElement {
  href?: string;
  muted?: boolean;
  defaultMuted?: boolean;
  volume?: number;
  currentTime?: number;
  duration?: number;
  paused?: boolean;
  ended?: boolean;
  src?: string;
  play?: () => Promise<void>;
  pause?: () => void;
  load?: () => void;
}

interface EventTarget {
  closest(selector: string): Element | null;
}

interface HTMLMediaElement {
  setSinkId?(sinkId: string): Promise<void>;
}

interface AudioContext {
  setSinkId?(sinkId: string): Promise<void>;
}

interface ScreenOrientation {
  lock?(orientation: string): Promise<void>;
}
interface LearnCampaignGoalSlice {
  done: number;
  total: number;
}
interface LearnCampaignGoal {
  words: LearnCampaignGoalSlice;
  sentences: LearnCampaignGoalSlice;
  read: LearnCampaignGoalSlice;
  sing: LearnCampaignGoalSlice;
  cleared: boolean;
}
interface LearnCampaignSkill {
  id: string;
  status: string;
  score?: number;
  attempts?: number;
  play_mode?: string;
}
interface LearnCampaignUnit {
  id: string;
  index: number;
  from_line: number;
  to_line: number;
  preview: string;
  line_indexes: number[];
  skills: LearnCampaignSkill[];
}
interface LearnCampaign {
  schema?: string;
  song_id: string;
  title?: string;
  artist?: string;
  language?: string;
  goal?: LearnCampaignGoal;
  units?: LearnCampaignUnit[];
  skills?: string[];
  mistakes?: number;
  pass_pct?: number;
  modes?: string[];
}
