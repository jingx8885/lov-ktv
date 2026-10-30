import SwiftUI

/// 听歌页：对齐网页 m.html 播放页的画法——歌词唱词占满主区，
/// 逐词卡拉OK填色（白→金），上注假名、下挂罗马音/词义，整句翻译垫底。
/// 封面标题收进顶栏，播控与切轨固定在底部，选歌收进上拉抽屉。
struct ListenView: View {
  @Environment(AppState.self) private var appState
  @Environment(LibraryStore.self) private var library
  @State private var sheetOpen = false
  @State private var lyricMode: LyricMode = .all

  var body: some View {
    NavigationStack {
      ZStack {
        KTVBackground()
        if appState.connection == nil {
          ContentUnavailableView {
            Label("未连接", systemImage: "headphones")
          } description: {
            Text("先在设置里连接服务器。")
          }
        } else if let client = appState.client {
          stage(client: client)
        }
      }
      .navigationTitle("听歌")
      .navigationBarTitleDisplayMode(.inline)
    }
    .task(id: appState.connection) {
      library.client = appState.client
      if library.client != nil { await library.search(page: 1) }
    }
    .onAppear {
      library.client = appState.client
      if library.songs.isEmpty, library.client != nil {
        Task { await library.search(page: 1) }
      }
    }
  }

  // MARK: - 舞台：顶栏 + 歌词主区 + 播控 + 抽屉把手

  private func stage(client: LovKTVClient) -> some View {
    let engine = appState.player
    return GeometryReader { geo in
      ZStack {
        karaoke(engine: engine, client: client)
          .safeAreaInset(edge: .bottom, spacing: 0) {
            pickerHandle(engine: engine)
          }
        if sheetOpen {
          Color.black.opacity(0.45)
            .ignoresSafeArea()
            .onTapGesture { closeSheet() }
            .transition(.opacity)
        }
        VStack {
          Spacer(minLength: 0)
          pickerSheet(engine: engine, client: client)
            .frame(height: sheetOpen ? min(geo.size.height * 0.64, 520) : 0)
            .clipped()
        }
        .ignoresSafeArea(.keyboard)
      }
      .animation(.spring(duration: 0.32), value: sheetOpen)
    }
  }

  private func closeSheet() {
    sheetOpen = false
    library.query = ""
  }

  private func karaoke(engine: PlayerEngine, client: LovKTVClient) -> some View {
    let script = engine.timeline?.script ?? .ja
    let mode = lyricMode.resolved(for: script)
    return VStack(spacing: 10) {
      headRow(engine: engine, script: script)
        .padding(.horizontal, KTVLayout.margin)
      lyricStage(engine: engine, mode: mode, script: script)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
      controlCard(engine: engine)
        .padding(.horizontal, KTVLayout.margin)
    }
    .padding(.top, 4)
  }

  /// 顶栏：封面 + 歌名歌手 + 歌词模式菜单（对齐 m.html player-head）
  private func headRow(engine: PlayerEngine, script: LyricScript) -> some View {
    HStack(spacing: 10) {
      ZStack {
        ArtView(seed: engine.detail?.displayTitle ?? "♪", size: 40)
        if engine.loading {
          ProgressView().tint(.white)
        }
      }
      VStack(alignment: .leading, spacing: 2) {
        Text(engine.detail?.displayTitle ?? "还没选歌")
          .font(.subheadline.weight(.bold))
          .lineLimit(1)
        Text(engine.detail?.displayArtist ?? "从下面挑一首")
          .font(.caption)
          .foregroundStyle(.secondary)
          .lineLimit(1)
      }
      Spacer(minLength: 8)
      Menu {
        Picker("歌词", selection: $lyricMode) {
          ForEach(LyricMode.allCases) { mode in
            Text(mode.title(for: script)).tag(mode)
          }
        }
      } label: {
        HStack(spacing: 4) {
          Image(systemName: "character.book.closed")
          Text(lyricMode.resolved(for: script).title(for: script))
            .font(.caption.weight(.semibold))
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(KTV.cardSoft.opacity(0.85), in: Capsule())
        .overlay(Capsule().stroke(KTV.accentColor.opacity(0.35), lineWidth: 1))
      }
      .accessibilityLabel("歌词显示模式")
    }
  }

  /// 歌词主区：整句列表垂直滚动，当前句居中；点句跳唱。
  private func lyricStage(engine: PlayerEngine, mode: LyricMode, script: LyricScript) -> some View {
    ScrollViewReader { proxy in
      ScrollView {
        LazyVStack(spacing: 18) {
          if engine.loading && engine.timeline == nil {
            ProgressView("正在对齐歌词…")
              .tint(.white)
              .padding(.top, 60)
          } else if let timeline = engine.timeline, !timeline.cues.isEmpty {
            let active = timeline.activeIndex(at: engine.currentMS)
            ForEach(Array(timeline.cues.enumerated()), id: \.element.id) { index, cue in
              KaraokeCueRow(
                cue: cue,
                script: script,
                mode: mode,
                now: engine.currentMS,
                state: cueState(index: index, active: active)
              ) {
                KTVHaptics.tap()
                engine.seekMS(cue.start_ms)
                engine.resume()
              }
              .id(cue.id)
            }
          } else {
            ContentUnavailableView {
              Label("暂无歌词", systemImage: "text.quote")
            } description: {
              Text(engine.songID == nil ? "从下方曲库挑一首开唱" : "这首歌还没有歌词时间轴")
            }
            .padding(.top, 40)
          }
        }
        .padding(.vertical, 200)
        .padding(.horizontal, KTVLayout.margin)
        .scrollTargetLayout()
      }
      .scrollIndicators(.hidden)
      .mask {
        LinearGradient(colors: [.clear, .black, .black, .clear],
                       startPoint: .top, endPoint: .bottom)
      }
      .onChange(of: engine.activeIndex) { _, idx in
        if let idx, let cue = engine.timeline?.cues[safe: idx] {
          withAnimation(.easeInOut(duration: 0.3)) {
            proxy.scrollTo(cue.id, anchor: .center)
          }
        }
      }
      .onChange(of: engine.songID) { _, _ in
        proxy.scrollTo(engine.timeline?.cues.first?.id, anchor: .center)
      }
    }
  }

  private func cueState(index: Int, active: Int?) -> CuePaintState {
    guard let active else { return .next }
    if index < active { return .done }
    if index == active { return .live }
    return .next
  }

  /// 底部播控卡：进度 + 回放上句/播放/下一首/快进 + 原唱伴奏切换
  private func controlCard(engine: PlayerEngine) -> some View {
    GlassCard(padding: 12) {
      VStack(spacing: 10) {
        VStack(spacing: 2) {
          Slider(value: Binding(
            get: { engine.durationMS > 0 ? Double(engine.currentMS) / Double(engine.durationMS) : 0 },
            set: { engine.seek(to: $0) }), in: 0...1)
          .tint(KTV.accentColor)
          HStack {
            Text(msText(engine.currentMS))
            Spacer()
            Text("−" + msText(max(engine.durationMS - engine.currentMS, 0)))
          }
          .font(.caption2.monospacedDigit())
          .foregroundStyle(.secondary)
        }
        HStack(spacing: 10) {
          NowActButton(icon: "arrow.counterclockwise", label: "回上句") {
            KTVHaptics.tap()
            if let idx = engine.activeIndex,
               let cue = engine.timeline?.cues[safe: max(idx - 1, 0)] {
              engine.seekMS(cue.start_ms)
            } else {
              engine.seekMS(max(engine.currentMS - 5000, 0))
            }
            engine.resume()
          }
          .disabled(engine.songID == nil)
          NowActButton(
            icon: engine.playing ? "pause.fill" : "play.fill",
            label: engine.playing ? "暂停" : "播放",
            prominent: true) {
              KTVHaptics.tap()
              engine.toggle()
            }
            .disabled(engine.songID == nil)
            .opacity(engine.songID == nil ? 0.5 : 1)
          NowActButton(icon: "forward.fill", label: "下一首") {
            KTVHaptics.tap()
            Task { await appState.skip() }
          }
          NowActButton(icon: "goforward.10", label: "快进") {
            KTVHaptics.tap()
            engine.seekForward()
          }
          .disabled(engine.songID == nil)
        }
        trackPicker(engine)
      }
    }
  }

  private func trackPicker(_ engine: PlayerEngine) -> some View {
    SegBar(items: [PlayerEngine.Track.original, .accompaniment],
           selection: Binding(
            get: { engine.track },
            set: { track in Task {
              if let error = await engine.setTrack(track) { appState.showStatus(error) }
            } }),
           title: { $0 == .original ? "原唱" : "伴奏" },
           disabled: { $0 == .accompaniment && engine.detail?.hasInstrumental != true })
  }

  /// 收起态把手：上拉选歌（对齐网页 player-sheet-grab）
  private func pickerHandle(engine: PlayerEngine) -> some View {
    Button {
      KTVHaptics.tap()
      sheetOpen = true
    } label: {
      HStack(spacing: 10) {
        RoundedRectangle(cornerRadius: 2, style: .continuous)
          .fill(Color.white.opacity(0.28))
          .frame(width: 36, height: 4)
        VStack(alignment: .leading, spacing: 1) {
          Text("曲库").font(.subheadline.weight(.bold))
          Text(engine.detail.map { "正在播 · \($0.displayTitle)" } ?? "上拉选歌")
            .font(.caption2)
            .foregroundStyle(.secondary)
            .lineLimit(1)
        }
        Spacer()
        Image(systemName: "chevron.up")
          .font(.subheadline.weight(.semibold))
          .foregroundStyle(.secondary)
      }
      .padding(.horizontal, KTVLayout.margin)
      .padding(.vertical, 10)
      .frame(maxWidth: .infinity)
      .background(.bar)
    }
    .buttonStyle(.ktvPress)
    .accessibilityLabel("打开曲库选歌")
  }

  /// 选歌抽屉：搜索 + 队列 + 曲库列表（对齐网页 player-sheet）
  private func pickerSheet(engine: PlayerEngine, client: LovKTVClient) -> some View {
    VStack(spacing: 10) {
      Button {
        KTVHaptics.tap()
        closeSheet()
      } label: {
        VStack(spacing: 6) {
          RoundedRectangle(cornerRadius: 2, style: .continuous)
            .fill(Color.white.opacity(0.28))
            .frame(width: 36, height: 4)
          HStack {
            Text("曲库").font(.headline.weight(.semibold))
            Spacer()
            Image(systemName: "chevron.down")
              .font(.subheadline.weight(.semibold))
              .foregroundStyle(.secondary)
          }
        }
        .padding(.horizontal, KTVLayout.margin)
      }
      .buttonStyle(.plain)
      .accessibilityLabel("收起曲库")

      SearchField(text: Bindable(library).query, placeholder: "搜索曲库")
        .padding(.horizontal, KTVLayout.margin)

      ScrollView {
        LazyVStack(spacing: 2) {
          if !appState.visibleQueue.isEmpty {
            Text("已点队列")
              .font(.caption.weight(.semibold))
              .foregroundStyle(.secondary)
              .frame(maxWidth: .infinity, alignment: .leading)
              .padding(.top, 4)
            ForEach(appState.visibleQueue) { song in
              pickerRow(song, playing: false, engine: engine, client: client)
            }
            Text("全部歌曲")
              .font(.caption.weight(.semibold))
              .foregroundStyle(.secondary)
              .frame(maxWidth: .infinity, alignment: .leading)
              .padding(.top, 10)
          }
          ForEach(library.songs.filter(\.isReady)) { song in
            pickerRow(song, playing: engine.songID == song.songID,
                      engine: engine, client: client)
              .task {
                if song.id == library.songs.filter(\.isReady).last?.id {
                  await library.loadMore()
                }
              }
          }
          if library.songs.isEmpty && !library.searching {
            Text("曲库还是空的，先去搜歌入库")
              .font(.caption)
              .foregroundStyle(.secondary)
              .padding(.top, 20)
          }
          if library.searching {
            ProgressView().tint(.white).padding(.top, 12)
          }
        }
        .padding(.horizontal, KTVLayout.margin)
        .padding(.bottom, 20)
      }
      .scrollDismissesKeyboard(.interactively)
    }
    .padding(.top, 10)
    .frame(maxWidth: .infinity)
    .background(.regularMaterial)
    .clipShape(UnevenRoundedRectangle(topLeadingRadius: 20, topTrailingRadius: 20))
    .shadow(color: .black.opacity(0.4), radius: 20, y: -6)
  }

  private func pickerRow(_ song: Song, playing: Bool,
                         engine: PlayerEngine, client: LovKTVClient) -> some View {
    Button {
      KTVHaptics.select()
      closeSheet()
      Task {
        if let error = await engine.open(song: song, client: client) {
          appState.showStatus(error)
        }
      }
    } label: {
      HStack(spacing: 12) {
        ArtView(seed: song.displayTitle, size: 40)
        VStack(alignment: .leading, spacing: 2) {
          Text(song.displayTitle).foregroundStyle(.primary).lineLimit(1)
          Text(song.displayArtist).font(.caption).foregroundStyle(.secondary)
        }
        Spacer()
        if playing {
          Image(systemName: "waveform").foregroundStyle(KTV.accentColor)
        }
      }
      .padding(.vertical, 6)
      .contentShape(Rectangle())
    }
    .buttonStyle(.ktvPress)
  }

  private func msText(_ ms: Int) -> String {
    let s = ms / 1000
    return String(format: "%d:%02d", s / 60, s % 60)
  }
}

// MARK: - 歌词模式（对齐 paint.js lyricModeForScript）

enum LyricMode: String, CaseIterable, Identifiable {
  case ja, zh, roma, all
  var id: String { rawValue }

  func resolved(for script: LyricScript) -> LyricMode {
    if script == .zh { return .all }
    if self == .roma, script == .en { return .all }
    if self == .roma, script != .ja { return .ja }
    return self
  }

  func title(for script: LyricScript) -> String {
    switch self {
    case .ja: return script == .ja ? "日语" : "原文"
    case .zh: return "翻译"
    case .roma: return "罗马音"
    case .all: return "全部"
    }
  }
}

// MARK: - 单行唱词：上句金色、当前句逐词填色、下句暗色（对齐 paint.js 三种皮肤）

enum CuePaintState { case done, live, next }

private struct KaraokeCueRow: View {
  let cue: LyricsTimeline.Cue
  let script: LyricScript
  let mode: LyricMode
  let now: Int
  let state: CuePaintState
  let onTap: () -> Void

  /// 金色与网页 --gold:#f5c16c 对齐
  private var gold: Color { KTV.amber }

  var body: some View {
    Button(action: onTap) {
      VStack(spacing: 3) {
        switch mode {
        case .zh:
          lineText(Text(cue.sub ?? cue.lineText))
        case .roma:
          lineText(Text(cue.lineRomaji.isEmpty ? cue.lineText : cue.lineRomaji))
        case .ja, .all:
          tokenLine()
          if mode == .all, let sub = cue.sub, !sub.isEmpty {
            Text(sub)
              .font(.system(size: live ? 15 : 13, weight: .semibold))
              .foregroundStyle(ink.opacity(0.92))
          }
        }
      }
      .frame(maxWidth: .infinity)
      .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
  }

  private var live: Bool { state == .live }

  private var ink: Color {
    switch state {
    case .done: return gold.opacity(0.72)
    case .live: return .white
    case .next: return .white.opacity(0.5)
    }
  }

  private var lineFont: Font {
    live ? .system(size: 21, weight: .bold) : .system(size: 15, weight: .semibold)
  }

  private func lineText(_ text: Text) -> some View {
    text.font(lineFont)
      .foregroundStyle(ink)
      .multilineTextAlignment(.center)
  }

  /// 逐词行：当前句渲染 token 级填充，其余句直接整行文本省排版开销
  @ViewBuilder
  private func tokenLine() -> some View {
    if !live {
      lineText(Text(cue.lineText))
    } else {
      TokenFlow(spacing: 0, rowSpacing: 10) {
        let tokens = cue.clusteredTokens
        if tokens.isEmpty {
          KaraokeFill(progress: tokenProgress(start: cue.start_ms, end: cue.end_ms, at: now)) {
            Text(cue.lineText).font(lineFont)
          }
        } else {
          ForEach(Array(tokens.enumerated()), id: \.offset) { index, tok in
            KaraokeToken(
              token: tok,
              mode: mode,
              script: script,
              progress: tokenProgress(start: tok.start_ms, end: tok.end_ms, at: now),
              baseFont: lineFont
            )
            if needsGap(tokens[index].display,
                        index + 1 < tokens.count ? tokens[index + 1].display : nil) {
              Text(" ").font(lineFont).fixedSize()
            }
          }
        }
      }
      .animation(.linear(duration: 0.03), value: now)
    }
  }

  /// 拉丁词之间、中日/拉丁边界补词距（paint.js tokenGapHtml）
  private func needsGap(_ surface: String, _ next: String?) -> Bool {
    guard let next, !next.isEmpty else { return false }
    if let first = next.first, ".,!?;:')\"".contains(first) { return false }
    let latin = isLatinSurface(surface)
    let nextLatin = isLatinSurface(next)
    if latin && nextLatin { return true }
    if script == .zh && latin != nextLatin { return true }
    return false
  }
}

// MARK: - 逐词单元：假名在上、词体卡拉OK填色、罗马音/词义在下

private struct KaraokeToken: View {
  let token: LyricsTimeline.Token
  let mode: LyricMode
  let script: LyricScript
  let progress: Double
  let baseFont: Font

  private var gold: Color { KTV.amber }
  private var latin: Bool { isLatinSurface(token.display) }
  private var showAnno: Bool { mode == .all }
  private var keepRt: Bool { script == .ja }
  private var keepRoma: Bool { showAnno && script == .ja }
  private var keepGloss: Bool { showAnno && script != .zh }

  /// 注音行：汉字词才给假名（paint.js rubyHtml 规则）
  private var reading: String {
    let r = token.reading ?? ""
    let text = token.text ?? token.display
    guard !r.isEmpty, r != text,
          isKanjiText(text), !isKanjiText(r) else { return "" }
    return r
  }

  private var roma: String {
    let r = token.romajiText.trimmingCharacters(in: .whitespaces)
    let text = token.display
    if r.isEmpty || r == text { return "" }
    if isLatinSurface(text), r.lowercased() == text.lowercased() { return "" }
    return r
  }

  var body: some View {
    VStack(spacing: 1) {
      if keepRt {
        Text(reading.isEmpty ? " " : reading)
          .font(.system(size: 9, weight: .bold))
          .foregroundStyle(gold)
          .frame(height: 11)
      }
      KaraokeFill(progress: progress) {
        Text(token.display).font(baseFont)
      }
      if keepRoma {
        Text(roma.isEmpty ? " " : roma)
          .font(.system(size: 11, weight: .semibold))
          .foregroundStyle(Color.white.opacity(0.88))
          .frame(height: 14)
      }
      if keepGloss {
        let gloss = token.glossText.trimmingCharacters(in: .whitespaces)
        Text(gloss.isEmpty ? " " : gloss)
          .font(.system(size: 10.5, weight: .bold))
          .foregroundStyle(Color(hex: "#ffd6a0").opacity(0.96))
          .frame(height: 13)
      }
    }
    .padding(.horizontal, latin ? 0 : 1.5)
    .padding(.trailing, latin ? 0.5 : 0)
  }
}

/// 白底金字逐词填充：fill 层用 mask 按进度裁宽（网页 .rb-fill 同款）
private struct KaraokeFill<Content: View>: View {
  let progress: Double
  @ViewBuilder var content: Content

  var body: some View {
    content
      .foregroundStyle(.white)
      .fixedSize()
      .overlay {
        content
          .foregroundStyle(KTV.amber)
          .fixedSize()
          .mask {
            GeometryReader { geo in
              Rectangle()
                .fill(.white)
                .frame(width: geo.size.width * min(max(progress, 0), 1))
                .frame(maxWidth: .infinity, alignment: .leading)
            }
          }
      }
  }
}

// MARK: - 自动换行的词排版：整行 token 超宽就换行居中（对应网页 flex-wrap）

private struct TokenFlow: Layout {
  var spacing: CGFloat = 0
  var rowSpacing: CGFloat = 10

  private func rows(in subviews: Subviews, proposal: ProposedViewSize,
                    sizes: [CGSize]) -> [(range: Range<Int>, size: CGSize)] {
    let maxWidth = proposal.width ?? .infinity
    var rows: [(Range<Int>, CGSize)] = []
    var start = 0
    var width: CGFloat = 0
    var height: CGFloat = 0
    for (index, size) in sizes.enumerated() {
      let item = index == start ? size.width : width + spacing + size.width
      if index > start, item > maxWidth {
        rows.append((start..<index, CGSize(width: width, height: height)))
        start = index
        width = size.width
        height = size.height
      } else {
        width = item
        height = max(height, size.height)
      }
    }
    if start < sizes.count {
      rows.append((start..<sizes.count, CGSize(width: width, height: height)))
    }
    return rows
  }

  func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews,
                    cache: inout ()) -> CGSize {
    let sizes = subviews.map { $0.sizeThatFits(.unspecified) }
    let rows = rows(in: subviews, proposal: proposal, sizes: sizes)
    let width = rows.map(\.size.width).max() ?? 0
    let height = rows.reduce(CGFloat(0)) { $0 + $1.size.height }
      + rowSpacing * CGFloat(max(rows.count - 1, 0))
    return CGSize(width: width, height: height)
  }

  func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize,
                     subviews: Subviews, cache: inout ()) {
    let sizes = subviews.map { $0.sizeThatFits(.unspecified) }
    var y = bounds.minY
    for row in rows(in: subviews, proposal: proposal, sizes: sizes) {
      var x = bounds.minX + (bounds.width - row.size.width) / 2
      for index in row.range {
        let size = sizes[index]
        subviews[index].place(
          at: CGPoint(x: x, y: y),
          anchor: .topLeading,
          proposal: ProposedViewSize(size))
        x += size.width + spacing
      }
      y += row.size.height + rowSpacing
    }
  }
}
