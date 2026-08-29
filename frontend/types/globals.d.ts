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
  hookAnalyser(audio: HTMLMediaElement | null, prev?: BandsHook | null, opts?: { ctx?: AudioContext; latencyHint?: string }): BandsHook | null;
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

interface LovStageFxApi {
  create(el: HTMLElement | null): StageFxHandle;
  bindParty(el: HTMLElement | null): void;
  celebrate(kind?: string): void;
  hookTexts(cues?: LyricCue[] | null): Set<string>;
  reduceMotion?: boolean;
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
  start(): boolean;
  togglePaused?: () => void | Promise<void>;
  settings?: () => void;
  back?: () => boolean;
  __ready?: boolean;
  __module?: boolean;
}

interface LovKtvPhoneBridge {
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
}

interface LovKtvNativeBridge {
  playMtv?: (url: string) => void;
  stopMtv?: () => void;
  clearLyrics?: () => void;
  pauseMtv?: () => void;
  resumeMtv?: () => void;
  durationMs?: () => number;
  positionMs?: () => number;
  playing?: () => boolean;
  seekMtv?: (positionMs: number) => void;
  openSetup?: () => void;
  startMic?: () => void;
  stopMic?: () => void;
  hasLanMic?: () => boolean;
  isMicLive?: () => boolean;
}

interface Window {
  webkitAudioContext?: typeof AudioContext;
  webkitOfflineAudioContext?: typeof OfflineAudioContext;
  LovBands?: LovBandsApi;
  LovMic?: LovMicApi;
  LovAec?: LovAecApi;
  LovTimeline?: LovTimelineApi;
  LovStageFx?: LovStageFxApi;
  LovKtvRemote?: LovKtvRemoteApi;
  LovKtvPhone?: LovKtvPhoneBridge;
  LovKtvNative?: LovKtvNativeBridge;
  LovKtvOnMic?: (ok: boolean, error?: string) => void;
  __lovktvNativeLan?: boolean;
  __lovktvPlayBooted?: boolean;
  __lovktvQrBooted?: boolean;
  confetti?: { create?: (canvas: HTMLElement, opts?: object) => unknown };
}

declare const LovBands: LovBandsApi;
declare const LovMic: LovMicApi;
declare const LovAec: LovAecApi;
declare const LovTimeline: LovTimelineApi;
declare const LovStageFx: LovStageFxApi;

declare function qrcode(typeNumber: number, errorCorrectionLevel: string): {
  addData(data: string): void;
  make(): void;
  createSvgTag(cellSize?: number, margin?: number): string;
};

interface Element {
  onclick: ((this: GlobalEventHandlers, ev: MouseEvent) => any) | null;
  dataset: DOMStringMap;
  style: CSSStyleDeclaration;
  disabled: boolean;
  hidden: boolean;
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
