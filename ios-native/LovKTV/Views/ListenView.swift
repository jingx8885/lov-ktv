import SwiftUI

/// 听歌页：大卡 + 歌词高亮 + 进度 + 播控 + 原唱/伴奏 + 选歌，竖向动线。
/// 播控与点歌台共用 NowActButton / SegBar，保证同一套画法。
struct ListenView: View {
  @Environment(AppState.self) private var appState
  @Environment(LibraryStore.self) private var library
  @State private var pickerQuery = ""

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
          player(client: client)
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

  @ViewBuilder
  private func player(client: LovKTVClient) -> some View {
    let engine = appState.player
    ScrollView {
      VStack(spacing: 14) {
        // 顶部大卡：封面 + 歌名 + 歌手
        GlassCard {
          VStack(spacing: 12) {
            GlowArtView(seed: engine.detail?.displayTitle ?? "♪", size: 160)
              .padding(.top, 6)
            VStack(spacing: 4) {
              Text(engine.detail?.displayTitle ?? "还没选歌")
                .font(.title3.weight(.bold))
              Text(engine.detail?.displayArtist ?? "从下面挑一首")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            }
          }
          .frame(maxWidth: .infinity)
        }

        // 歌词时间轴：当前行高亮居中
        if let timeline = engine.timeline, !timeline.cues.isEmpty {
          GlassCard(padding: 12) {
            ScrollViewReader { lyricProxy in
              ScrollView {
                VStack(spacing: 12) {
                  ForEach(timeline.cues) { cue in
                    LyricLine(cue: cue,
                              active: timeline.activeIndex(at: engine.currentMS) == cue.start_ms,
                              onTap: {
                                engine.seekMS(cue.start_ms)
                                engine.resume()
                              })
                      .id(cue.start_ms)
                  }
                }
                .padding(.vertical, 18)
              }
              .frame(maxHeight: 220)
              .mask {
                LinearGradient(colors: [.clear, .black, .black, .clear],
                               startPoint: .top, endPoint: .bottom)
              }
              .onChange(of: engine.activeIndex) { _, idx in
                if let idx, let cue = timeline.cues[safe: idx] {
                  withAnimation(.easeInOut(duration: 0.3)) {
                    lyricProxy.scrollTo(cue.start_ms, anchor: .center)
                  }
                }
              }
            }
          }
        }

        // 进度 + 播控 + 切换
        GlassCard {
          VStack(spacing: 12) {
            VStack(spacing: 4) {
              Slider(value: Binding(
                get: { engine.durationMS > 0 ? Double(engine.currentMS) / Double(engine.durationMS) : 0 },
                set: { engine.seek(to: $0) }), in: 0...1)
              .tint(KTV.accentColor)
              HStack {
                Text(msText(engine.currentMS))
                Spacer()
                Text(msText(engine.durationMS))
              }
              .font(.caption2.monospacedDigit())
              .foregroundStyle(.secondary)
            }
            HStack(spacing: 10) {
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
            }
            trackPicker(engine)
          }
        }

        // 选歌
        VStack(alignment: .leading, spacing: 8) {
          Text("挑一首").font(.headline.weight(.semibold))
          SearchField(text: $pickerQuery, placeholder: "过滤曲库")
          ForEach(library.songs.filter {
            $0.isReady && (pickerQuery.isEmpty
              || $0.displayTitle.localizedCaseInsensitiveContains(pickerQuery)
              || $0.displayArtist.localizedCaseInsensitiveContains(pickerQuery))
          }) { song in
            Button {
              KTVHaptics.select()
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
                if engine.songID == song.songID {
                  Image(systemName: "waveform").foregroundStyle(KTV.accentColor)
                }
              }
              .padding(.vertical, 6)
            }
            .buttonStyle(.ktvPress)
          }
        }
        .padding(.horizontal, 4)
      }
      .padding(.horizontal, KTVLayout.margin)
      .padding(.bottom, 100)
    }
  }

  private func trackPicker(_ engine: PlayerEngine) -> some View {
    SegBar(items: [PlayerEngine.Track.original, .accompaniment],
           selection: Binding(
            get: { engine.track },
            set: { track in Task { _ = await engine.setTrack(track) } }),
           title: { $0 == .original ? "原唱" : "伴奏" },
           disabled: { $0 == .accompaniment && engine.detail?.hasInstrumental != true })
  }

  private func msText(_ ms: Int) -> String {
    let s = ms / 1000
    return String(format: "%d:%02d", s / 60, s % 60)
  }
}

/// 单行歌词：激活时主题色放大高亮，点击 seek
private struct LyricLine: View {
  let cue: LyricsTimeline.Cue
  let active: Bool
  let onTap: () -> Void

  var body: some View {
    Button(action: onTap) {
      VStack(spacing: 4) {
        Text(cue.display)
          .font(active ? .title3.weight(.bold) : .body.weight(.medium))
          .foregroundStyle(active ? KTV.accentColor : Color.secondary)
          .multilineTextAlignment(.center)
        if let r = cue.romaji, !r.isEmpty {
          Text(r).font(.caption).foregroundStyle(.secondary)
        }
        if let z = cue.sub, !z.isEmpty {
          Text(z).font(.caption).foregroundStyle(.secondary)
        }
      }
      .frame(maxWidth: .infinity)
      .padding(.vertical, 4)
      .background {
        if active {
          RoundedRectangle(cornerRadius: 12, style: .continuous)
            .fill(KTV.accentColor.opacity(0.1))
        }
      }
      .animation(.easeInOut(duration: 0.25), value: active)
    }
    .buttonStyle(.plain)
  }
}
