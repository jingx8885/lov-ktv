import SwiftUI

/// 听歌页：挑一首 ready 的歌直接播，原唱/伴奏双轨 + 卡拉OK时间轴。
struct ListenView: View {
  @Environment(AppState.self) private var appState
  @Environment(LibraryStore.self) private var library
  @State private var pickerQuery = ""

  var body: some View {
    NavigationStack {
      if appState.connection == nil {
        ContentUnavailableView {
          Label("未连接", systemImage: "headphones")
        } description: {
          Text("先在设置里连接服务器。")
        }
        .navigationTitle("听歌")
      } else if let client = appState.client {
        player(client: client)
          .navigationTitle("听歌")
      }
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

  @ViewBuilder
  private func player(client: LovKTVClient) -> some View {
    let engine = appState.player
    ScrollViewReader { proxy in
      List {
        // 播放器卡
        Section {
          VStack(spacing: 16) {
            ArtView(seed: engine.detail?.displayTitle ?? "♪", size: 120)
              .padding(.top, 8)
            VStack(spacing: 4) {
              Text(engine.detail?.displayTitle ?? "还没选歌")
                .font(.title3.weight(.semibold))
              Text(engine.detail?.displayArtist ?? "从下面挑一首")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            }
            // 进度
            VStack(spacing: 4) {
              Slider(value: Binding(
                get: { engine.durationMS > 0 ? Double(engine.currentMS) / Double(engine.durationMS) : 0 },
                set: { engine.seek(to: $0) }), in: 0...1)
              HStack {
                Text(msText(engine.currentMS))
                Spacer()
                Text(msText(engine.durationMS))
              }
              .font(.caption2.monospacedDigit())
              .foregroundStyle(.secondary)
            }
            // 控制：原唱/伴奏 + 播放
            HStack(spacing: 20) {
              Picker("音轨", selection: trackBinding) {
                Text("原唱").tag(PlayerEngine.Track.original)
                Text("伴奏").tag(PlayerEngine.Track.accompaniment)
              }
              .pickerStyle(.segmented)
              .frame(width: 180)
              .disabled(engine.detail?.hasInstrumental != true)

              Button { engine.toggle() } label: {
                Image(systemName: engine.playing ? "pause.fill" : "play.fill")
                  .font(.title2)
                  .frame(width: 56, height: 56)
                  .background(.primary.opacity(0.08), in: Circle())
              }
              .disabled(engine.songID == nil)
            }
            if engine.detail?.hasInstrumental != true, engine.songID != nil {
              Text("这首歌还没有伴奏轨").font(.caption).foregroundStyle(.secondary)
            }
          }
          .frame(maxWidth: .infinity)
          .padding(.vertical, 8)
        }

        // 歌词时间轴；点词收进单词本（自建服）
        if let timeline = engine.timeline {
          Section("歌词 · 点词进单词本") {
            ForEach(timeline.cues) { cue in
              LyricLineView(cue: cue, active: timeline.activeIndex(at: engine.currentMS) == cue.start_ms,
                            currentMS: engine.currentMS,
                            onTapWord: { collectWord($0, cue: cue) })
                .id(cue.start_ms)
            }
          }
        }

        // 选歌
        Section("挑一首") {
          TextField("过滤曲库", text: $pickerQuery)
          ForEach(library.songs.filter {
            $0.isReady && (pickerQuery.isEmpty
              || $0.displayTitle.localizedCaseInsensitiveContains(pickerQuery)
              || $0.displayArtist.localizedCaseInsensitiveContains(pickerQuery))
          }) { song in
            Button {
              Task {
                if let error = await engine.open(song: song, client: client) {
                  appState.showStatus(error)
                }
              }
            } label: {
              HStack {
                ArtView(seed: song.displayTitle, size: 36)
                VStack(alignment: .leading) {
                  Text(song.displayTitle).foregroundStyle(.primary).lineLimit(1)
                  Text(song.displayArtist).font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                if engine.songID == song.songID {
                  Image(systemName: "waveform").foregroundStyle(.tint)
                }
              }
            }
          }
        }
      }
      .listStyle(.insetGrouped)
      .onChange(of: engine.activeIndex) { _, idx in
        if let idx, let cue = engine.timeline?.cues[safe: idx] {
          withAnimation { proxy.scrollTo(cue.start_ms, anchor: .center) }
        }
      }
    }
  }

  private var trackBinding: Binding<PlayerEngine.Track> {
    Binding(
      get: { appState.player.track },
      set: { track in
        Task {
          if let error = await appState.player.setTrack(track) {
            appState.showStatus(error)
          }
        }
      })
  }

  @State private var collected: Set<String> = []

  private func collectWord(_ token: LyricsTimeline.Token, cue: LyricsTimeline.Cue) {
    guard let client = appState.client, let songID = appState.player.songID else { return }
    let text = token.display
    guard !text.isEmpty else { return }
    collected.insert(text + "\(token.start_ms)")
    Task {
      let word = SongWord(word_id: "\(songID):\(text)", language: appState.player.detail?.language ?? "",
                          text: text, zh: "", romaji: cue.romaji ?? "",
                          line_text: cue.display,
                          start_ms: cue.start_ms, end_ms: cue.end_ms)
      _ = try? await client.collectWord(word, songID: songID, songTitle: appState.player.detail?.displayTitle ?? "")
      appState.showStatus("\(text) 已进单词本")
    }
  }

  private func msText(_ ms: Int) -> String {
    let s = ms / 1000
    return String(format: "%d:%02d", s / 60, s % 60)
  }
}

/// 单行歌词：当前行高亮 + 逐词进度（有 tokens 时按时间填色）
private struct LyricLineView: View {
  let cue: LyricsTimeline.Cue
  let active: Bool
  let currentMS: Int

  var body: some View {
    VStack(alignment: .leading, spacing: 3) {
      if let tokens = cue.tokens, !tokens.isEmpty, active {
        // 逐词卡拉OK：已唱的词上色
        tokensRow(tokens)
      } else {
        Text(cue.display)
          .font(active ? .title3.weight(.semibold) : .body)
          .foregroundStyle(active ? .primary : .secondary)
      }
      if let romaji = cue.romaji, !romaji.isEmpty {
        Text(romaji).font(.caption).foregroundStyle(.secondary)
      }
      if let sub = cue.sub, !sub.isEmpty {
        Text(sub).font(.caption).foregroundStyle(.secondary)
      }
    }
    .padding(.vertical, 2)
  }

  private func tokensRow(_ tokens: [LyricsTimeline.Token]) -> some View {
    // tokens 简单横排；唱过的词用主题色；点词收进单词本
    HStack(spacing: 0) {
      ForEach(Array(tokens.enumerated()), id: \.offset) { _, token in
        Button {
          onTapWord?(token)
        } label: {
          Text(token.display)
            .font(.title3.weight(.semibold))
            .foregroundStyle(currentMS >= token.start_ms ? Color.accentColor : Color.secondary)
        }
        .buttonStyle(.plain)
      }
    }
  }

  var onTapWord: ((LyricsTimeline.Token) -> Void)? = nil
}

extension Array {
  subscript(safe index: Int) -> Element? {
    indices.contains(index) ? self[index] : nil
  }
}
