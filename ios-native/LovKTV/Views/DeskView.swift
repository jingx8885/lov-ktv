import SwiftUI

/// 点歌台：对齐 m.html 的 desk 页——同一屏里"正在唱 + 播控 + 已点/曲库/在线/歌词/歌单"，
/// 不用切 tab 就能完成点歌全流程。
struct DeskView: View {
  @Environment(AppState.self) private var appState
  @Environment(LibraryStore.self) private var library
  var onGoSettings: () -> Void
  var onGoLearn: () -> Void
  @Binding var listeningTitle: String?

  @State private var pane: DeskPane = .queue
  @State private var confirmSkip = false
  @State private var showMix = false

  // 歌曲动作
  @State private var actionSong: Song?
  @State private var playlistSong: Song?
  @State private var reportSong: Song?
  @State private var reportReason = ""
  @State private var imported: Set<String> = []

  // 歌词面板
  @State private var lyricTimeline: LyricsTimeline?
  @State private var lyricSongID = ""
  @State private var lyricLoading = false

  enum DeskPane: String, CaseIterable {
    case queue = "已点", library = "曲库", online = "在线", lyrics = "歌词", playlists = "歌单"
  }

  var body: some View {
    NavigationStack {
      ZStack {
        KTVBackground()
        if appState.connection == nil {
          NotConnectedView(onConnect: onGoSettings)
        } else {
          desk
        }
      }
      .navigationTitle("点歌")
      .navigationBarTitleDisplayMode(.inline)
      .toolbar {
        if appState.connection != nil {
          ToolbarItem(placement: .topBarTrailing) {
            Button { showMix = true } label: {
              Image(systemName: "slider.horizontal.3")
            }
            .accessibilityLabel("房间设置")
          }
        }
      }
      .sheet(isPresented: $showMix) { RoomMixSheet() }
      .sheet(item: $playlistSong) { song in AddToPlaylistSheet(song: song) }
      .confirmationDialog("切换到下一首？当前歌曲会立即停止。", isPresented: $confirmSkip) {
        Button("下一首", role: .destructive) { Task { await appState.skip() } }
        Button("取消", role: .cancel) {}
      }
      .confirmationDialog(
        actionSong.map { "\($0.displayTitle) · \($0.displayArtist)" } ?? "",
        isPresented: .constant(actionSong != nil),
        titleVisibility: .visible,
        presenting: actionSong
      ) { song in
        if song.isReady {
          Button("手机试听") { previewLocal(song) }
        }
        Button("加入歌单") {
          playlistSong = song
          actionSong = nil
        }
        Button("屏蔽", role: .destructive) {
          appState.block(song); actionSong = nil
        }
        Button("举报并屏蔽", role: .destructive) {
          reportSong = song; actionSong = nil
        }
        Button("取消", role: .cancel) { actionSong = nil }
      }
      .alert("举报原因", isPresented: .constant(reportSong != nil), presenting: reportSong) { song in
        TextField("不当内容、侵权或其他（最多 500 字）", text: $reportReason, axis: .vertical)
        Button("提交举报", role: .destructive) {
          let reason = reportReason.trimmingCharacters(in: .whitespacesAndNewlines)
          if !reason.isEmpty {
            Task { await appState.reportAndBlock(song, reason: reason) }
          }
          reportReason = ""; reportSong = nil
        }
        Button("取消", role: .cancel) { reportReason = ""; reportSong = nil }
      }
    }
    .task {
      async let _ = appState.listenRoomSnapshots()
      while !Task.isCancelled {
        if appState.connection != nil {
          if let error = await appState.refresh() { appState.showStatus(error) }
        }
        try? await Task.sleep(for: .seconds(3))
      }
    }
    .task(id: appState.connection) {
      library.client = appState.client
      if library.client != nil { await library.search(page: 1) }
    }
    .task(id: appState.room?.now_playing?.songID) {
      guard let id = appState.room?.now_playing?.songID, !id.isEmpty,
            id != lyricSongID else { return }
      lyricSongID = id
      await loadLyrics(for: id)
    }
  }

  // MARK: - 整体

  private var desk: some View {
    VStack(spacing: 0) {
      nowBar
        .padding(.horizontal, KTVLayout.margin)
        .padding(.top, 4)
      SegBar(items: DeskPane.allCases, selection: $pane,
             title: { $0.rawValue },
             badge: { $0 == .queue ? appState.visibleQueue.count : nil })
        .padding(.horizontal, KTVLayout.margin)
        .padding(.top, 10)
        .padding(.bottom, 6)
      paneContent
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
  }

  @ViewBuilder
  private var paneContent: some View {
    switch pane {
    case .queue: queuePane
    case .library: libraryPane
    case .online: onlinePane
    case .lyrics: lyricsPane
    case .playlists: playlistsPane
    }
  }

  // MARK: - 正在唱卡

  private var nowBar: some View {
    GlassCard(padding: 10) {
      HStack(spacing: 10) {
        ArtView(seed: appState.room?.now_playing?.displayTitle ?? "♪",
                size: 38)
          .opacity(appState.room?.now_playing == nil ? 0.4 : 1)
        VStack(alignment: .leading, spacing: 2) {
          HStack(spacing: 5) {
            NeonTag(text: appState.room?.now_playing == nil ? "空闲"
                    : appState.room?.paused == true ? "已暂停" : "正在唱",
                    color: appState.room?.now_playing == nil ? .secondary
                    : appState.room?.paused == true ? .orange : KTV.lime)
            Text("房间 \(appState.connection?.room ?? "")")
              .font(.caption2)
              .foregroundStyle(.secondary)
          }
          Text(nowLine)
            .font(.subheadline.weight(.semibold))
            .lineLimit(1)
        }
        Spacer(minLength: 6)
        nowButton(icon: appState.room?.paused == true ? "play.fill" : "pause.fill",
                  prominent: true) {
          KTVHaptics.tap()
          Task { await appState.togglePlay() }
        }
        .disabled(appState.room?.now_playing == nil)
        .opacity(appState.room?.now_playing == nil ? 0.45 : 1)
        .accessibilityLabel(appState.room?.paused == true ? "继续" : "暂停")
        nowButton(icon: "forward.fill", prominent: false) {
          KTVHaptics.tap()
          confirmSkip = true
        }
        .accessibilityLabel("切歌")
      }
    }
  }

  private var nowLine: String {
    guard let now = appState.room?.now_playing else {
      return "还没在唱 · 从曲库点一首"
    }
    return "\(now.displayTitle) · \(now.displayArtist)"
  }

  private func nowButton(icon: String, prominent: Bool,
                         action: @escaping () -> Void) -> some View {
    Button(action: action) {
      Image(systemName: icon)
        .font(.system(size: 13, weight: .bold))
        .frame(width: 32, height: 32)
        .foregroundStyle(prominent ? Color.white : Color.white.opacity(0.75))
        .background {
          if prominent {
            Circle().fill(KTV.accent)
              .shadow(color: KTV.pink.opacity(0.3), radius: 5, y: 2)
          } else {
            Circle().fill(Color.white.opacity(0.07))
          }
        }
        .contentTransition(.symbolEffect(.replace))
    }
    .buttonStyle(.ktvPress)
  }

  // MARK: - 已点队列

  private var queuePane: some View {
    ScrollView {
      LazyVStack(spacing: 0) {
        ForEach(Array(appState.visibleQueue.enumerated()), id: \.element.queueItemID) { index, song in
          QueueRow(index: index, song: song,
                   isNowPlaying: index == (appState.room?.now_index ?? 0),
                   canBump: appState.room?.canBump(at: index) == true,
                   onPlay: { Task { await appState.playItem(song.queueItemID) } },
                   onBump: { Task { await appState.bumpItem(song.queueItemID) } })
          if index < appState.visibleQueue.count - 1 {
            Divider().padding(.leading, 68)
          }
        }
      }
      .padding(.horizontal, 4)
      .background {
        RoundedRectangle(cornerRadius: KTVLayout.cardRadius, style: .continuous)
          .fill(KTV.card.opacity(0.55))
      }
      .padding(.horizontal, KTVLayout.margin)
      .padding(.bottom, 100)

      if appState.visibleQueue.isEmpty {
        DeskEmpty(icon: "music.note.list", title: "还没点歌",
                  hint: "点过的歌会排在这里", actionTitle: "去曲库加点") {
          pane = .library
        }
        .padding(.top, 36)
      }
    }
    .refreshable { _ = await appState.refresh() }
  }

  // MARK: - 曲库（入库歌曲：搜索 + 点歌 + 收藏 + 更多）

  private var queuedIDs: Set<String> {
    Set((appState.room?.queue ?? []).compactMap(\.song_id))
  }

  private var libraryPane: some View {
    VStack(spacing: 8) {
      SearchField(text: Bindable(library).query, placeholder: "搜歌名 / 歌星")
        .padding(.horizontal, KTVLayout.margin)
      List {
        ForEach(library.songs.filter { !appState.isHidden($0) }) { song in
          SongRow(song: song,
                  showsEnqueue: true,
                  showsFavorite: appState.connection?.mode == .selfHosted,
                  onEnqueue: { enqueue(song) },
                  onFavorite: { Task { await toggleFavorite(song) } },
                  onMore: { actionSong = song },
                  enqueued: queuedIDs.contains(song.songID))
        }
        if library.songs.isEmpty && !library.searching {
          ContentUnavailableView(
            library.query.isEmpty ? "曲库还是空的" : "没有找到相关歌曲",
            systemImage: "music.note.list",
            description: Text(library.query.isEmpty
                              ? "去「在线」搜一首歌入库。" : "换个歌名或歌手试试。"))
          .listRowSeparator(.hidden)
          .listRowBackground(Color.clear)
        }
        if library.hasMore {
          Button { Task { await library.loadMore() } } label: {
            HStack {
              Spacer()
              if library.searching { ProgressView() } else { Text("加载更多") }
              Spacer()
            }
          }
          .listRowSeparator(.hidden)
        }
      }
      .listStyle(.plain)
      .scrollContentBackground(.hidden)
      .scrollDismissesKeyboard(.interactively)
      .refreshable { await library.search(page: 1) }
    }
  }

  // MARK: - 在线搜

  private var onlinePane: some View {
    VStack(spacing: 8) {
      SearchField(text: Bindable(library).onlineQuery, placeholder: "歌名 / 歌手")
        .padding(.horizontal, KTVLayout.margin)
      List {
        ForEach(library.hits) { hit in
          OnlineHitRow(hit: hit,
                       previewing: appState.stream.playingID == hit.id,
                       imported: imported.contains(hit.id),
                       onPreview: { previewOnline(hit) },
                       onImport: { importHit(hit) })
        }
        if library.hits.isEmpty && !library.searchingOnline {
          ContentUnavailableView(
            library.onlineQuery.isEmpty ? "输入歌名在线搜" : "没有搜到",
            systemImage: "globe",
            description: Text(library.onlineError
                              ?? (library.onlineQuery.isEmpty
                                  ? "网易 / B站 / Mugen 等源的结果会出现在这里。" : "换个关键词试试。")))
          .listRowSeparator(.hidden)
          .listRowBackground(Color.clear)
        }
        if library.onlineHasMore {
          Button { Task { await library.loadMoreOnline() } } label: {
            HStack { Spacer(); Text("加载更多"); Spacer() }
          }
          .listRowSeparator(.hidden)
        }
        if library.searchingOnline {
          HStack { Spacer(); ProgressView(); Spacer() }
            .listRowSeparator(.hidden)
        }
      }
      .listStyle(.plain)
      .scrollContentBackground(.hidden)
      .scrollDismissesKeyboard(.interactively)
    }
  }

  // MARK: - 歌词

  private var lyricsPane: some View {
    VStack(spacing: 10) {
      // 头部：正在播放 + 歌词模式 + 练这首
      HStack(alignment: .top) {
        VStack(alignment: .leading, spacing: 2) {
          Text("正在播放")
            .font(.caption2)
            .foregroundStyle(.secondary)
          Text(lyricHeaderTitle)
            .font(.subheadline.weight(.semibold))
            .lineLimit(1)
        }
        Spacer()
        HStack(spacing: 0) {
          stepperButton("-") {
            Task { await appState.setMix(lyricSize: max(10, (appState.room?.lyric_size ?? 30) - 10)) }
          }
          .accessibilityLabel("调小字号")
          Text("\(appState.room?.lyric_size ?? 30)%")
            .font(.caption.monospacedDigit().weight(.semibold))
            .foregroundStyle(.secondary)
            .frame(width: 42)
          stepperButton("+") {
            Task { await appState.setMix(lyricSize: min(250, (appState.room?.lyric_size ?? 30) + 10)) }
          }
          .accessibilityLabel("调大字号")
        }
        .background(KTV.cardSoft.opacity(0.85), in: Capsule())
        .overlay(Capsule().stroke(Color.secondary.opacity(0.25), lineWidth: 1))
        ChipButton(title: "练这首", icon: "graduationcap", style: .tinted) {
          onGoLearn()
        }
        .disabled(appState.room?.now_playing == nil)
      }
      .padding(.horizontal, KTVLayout.margin)

      SegBar(items: ["ja", "zh", "roma", "all"], selection: lyricModeBinding,
             title: { ["ja": "日语", "zh": "翻译", "roma": "罗马音", "all": "全部"][$0] ?? $0 })
        .padding(.horizontal, KTVLayout.margin)

      lyricList
    }
  }

  private var lyricHeaderTitle: String {
    guard let now = appState.room?.now_playing else { return "还没在唱" }
    return "\(now.displayTitle) · \(now.displayArtist)"
  }

  private func stepperButton(_ symbol: String, action: @escaping () -> Void) -> some View {
    Button(action: action) {
      Text(symbol)
        .font(.body.weight(.bold))
        .foregroundStyle(KTV.accentColor)
        .frame(width: 30, height: 26)
        .contentShape(Rectangle())
    }
    .buttonStyle(.ktvPress)
  }

  private var lyricModeBinding: Binding<String> {
    Binding(
      get: { appState.room?.lyric_mode ?? "all" },
      set: { mode in Task { await appState.setMix(lyricMode: mode) } })
  }

  @ViewBuilder
  private var lyricList: some View {
    if lyricLoading {
      Spacer()
      ProgressView()
      Spacer()
    } else if let timeline = lyricTimeline, !timeline.cues.isEmpty {
      ScrollView {
        LazyVStack(spacing: 4) {
          ForEach(timeline.cues) { cue in
            DeskLyricLine(cue: cue, mode: appState.room?.lyric_mode ?? "all")
          }
        }
        .padding(.horizontal, KTVLayout.margin)
        .padding(.bottom, 100)
      }
      .mask {
        LinearGradient(colors: [.clear, .black],
                       startPoint: .top, endPoint: .init(x: 0.5, y: 0.06))
          .ignoresSafeArea(.container, edges: .top)
      }
    } else {
      Spacer()
      DeskEmpty(icon: "text.quote",
                title: appState.room?.now_playing == nil ? "还没在唱" : "这首歌没有歌词",
                hint: appState.room?.now_playing == nil ? "点一首有歌词的歌试试" : "歌词文件还没准备好",
                actionTitle: nil, action: nil)
      Spacer()
    }
  }

  private func loadLyrics(for songID: String) async {
    lyricLoading = true
    lyricTimeline = nil
    if let client = appState.client {
      lyricTimeline = await client.fetchTimeline(songID: songID)
    }
    lyricLoading = false
  }

  // MARK: - 歌单

  private var playlistsPane: some View {
    PlaylistsView()
  }

  // MARK: - 动作

  private func enqueue(_ song: Song) {
    KTVHaptics.tap()
    Task { await appState.enqueue(song: song) }
  }

  private func toggleFavorite(_ song: Song) async {
    if let error = await library.toggleFavorite(song) {
      appState.showStatus(error)
    }
  }

  private func previewLocal(_ song: Song) {
    actionSong = nil
    listeningTitle = song.displayTitle
    Task {
      if let error = await appState.preview.play(song: song, client: appState.client) {
        listeningTitle = nil
        appState.showStatus(error)
      }
    }
  }

  private func previewOnline(_ hit: SearchHit) {
    Task {
      if let client = appState.client,
         let error = await appState.stream.toggle(hit, client: client) {
        appState.showStatus(error)
      }
    }
  }

  private func importHit(_ hit: SearchHit) {
    guard let client = appState.client else { return }
    imported.insert(hit.id)
    Task {
      do {
        _ = try await client.importHit(hit)
        appState.showStatus("已开始导入，可在曲库面板查看进度")
        await library.search(page: 1)
      } catch {
        imported.remove(hit.id)
        appState.showStatus(error.localizedDescription)
      }
    }
  }
}

// MARK: - 队列行

private struct QueueRow: View {
  let index: Int
  let song: Song
  let isNowPlaying: Bool
  let canBump: Bool
  let onPlay: () -> Void
  let onBump: () -> Void

  var body: some View {
    HStack(spacing: 12) {
      ZStack {
        ArtView(seed: song.displayTitle, size: KTVLayout.artSize)
        if isNowPlaying {
          Circle().fill(KTV.lime).frame(width: 13, height: 13)
            .overlay(Circle().stroke(.white, lineWidth: 2))
            .offset(x: 15, y: 15)
        }
      }
      VStack(alignment: .leading, spacing: 3) {
        Text(song.displayTitle)
          .font(.body.weight(.medium))
          .lineLimit(1)
        HStack(spacing: 6) {
          if isNowPlaying {
            NeonTag(text: "正在唱", color: KTV.lime)
          } else if let badge = song.badge {
            NeonTag(text: badge.text, color: badge.isError ? .red : .orange)
          }
          Text(song.displayArtist)
            .font(.caption).foregroundStyle(.secondary).lineLimit(1)
        }
      }
      Spacer(minLength: 8)
      ChipButton(title: "唱这首", icon: "play.fill",
                 style: .tinted,
                 tint: isNowPlaying ? KTV.lime : KTV.accentColor,
                 action: onPlay)
        .disabled(isNowPlaying)
      if canBump {
        IconCircleButton(icon: "arrow.up.to.line", tint: .secondary, filled: false,
                         action: onBump)
          .accessibilityLabel("置顶")
      }
    }
    .padding(.horizontal, 10).padding(.vertical, 8)
    .background {
      if isNowPlaying {
        RoundedRectangle(cornerRadius: KTVLayout.rowRadius, style: .continuous)
          .fill(KTV.lime.opacity(0.08))
      }
    }
  }
}

// MARK: - 歌词行（点歌台歌词面板：按房间 lyric_mode 显示）

private struct DeskLyricLine: View {
  let cue: LyricsTimeline.Cue
  let mode: String

  var body: some View {
    VStack(alignment: .leading, spacing: 3) {
      switch mode {
      case "ja":
        main(cue.display)
        if let r = cue.romaji, !r.isEmpty { sub(r) }
      case "zh":
        main(cue.sub ?? cue.display)
      case "roma":
        main(cue.romaji ?? cue.display)
      default:
        main(cue.display)
        if let r = cue.romaji, !r.isEmpty { sub(r) }
        if let z = cue.sub, !z.isEmpty { sub(z) }
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(.vertical, 5)
  }

  private func main(_ text: String) -> some View {
    Text(text)
      .font(.body.weight(.medium))
      .foregroundStyle(.primary)
  }
  private func sub(_ text: String) -> some View {
    Text(text)
      .font(.caption)
      .foregroundStyle(.secondary)
  }
}

// MARK: - 空态

struct DeskEmpty: View {
  let icon: String
  let title: String
  var hint: String? = nil
  var actionTitle: String? = nil
  var action: (() -> Void)? = nil

  var body: some View {
    VStack(spacing: 12) {
      Image(systemName: icon)
        .font(.system(size: 34, weight: .light))
        .foregroundStyle(KTV.accentVertical)
      Text(title).font(.subheadline.weight(.medium))
      if let hint {
        Text(hint).font(.caption).foregroundStyle(.secondary)
      }
      if let actionTitle, let action {
        ChipButton(title: actionTitle, style: .filled, action: action)
          .padding(.top, 4)
      }
    }
    .frame(maxWidth: .infinity)
    .padding(.vertical, 24)
  }
}
