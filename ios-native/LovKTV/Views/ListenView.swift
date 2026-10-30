import SwiftUI

/// 听歌页：大卡 + 歌词高亮 + 进度 + 播控 + 原唱/伴奏胶囊 + 选歌，竖向动线。
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
      ScrollView {
        VStack(spacing: 16) {
          // 顶部大卡：封面 + 歌名 + 歌手
          GlassCard {
            VStack(spacing: 14) {
              GlowArtView(seed: engine.detail?.displayTitle ?? "♪", size: 200)
                .padding(.top, 8)
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
            GlassCard(padding: 14) {
              ScrollViewReader { lyricProxy in
                ScrollView {
                  VStack(spacing: 14) {
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
                  .padding(.vertical, 20)
                }
                .frame(maxHeight: 240)
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
            VStack(spacing: 14) {
              VStack(spacing: 4) {
                Slider(value: Binding(
                  get: { engine.durationMS > 0 ? Double(engine.currentMS) / Double(engine.durationMS) : 0 },
                  set: { engine.seek(to: $0) }), in: 0...1)
                .tint(KTV.pink)
                HStack {
                  Text(msText(engine.currentMS))
                  Spacer()
                  Text(msText(engine.durationMS))
                }
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.secondary)
              }
              HStack(spacing: 28) {
                BigRoundButton(
                  icon: engine.playing ? "pause.fill" : "play.fill",
                  tint: KTV.lime, size: 64) {
                  engine.toggle()
                }
                .disabled(engine.songID == nil)
                .accessibilityLabel(engine.playing ? "暂停" : "播放")

                BigRoundButton(icon: "forward.fill", tint: KTV.cyan, size: 56) {
                  Task { await appState.skip() }
                }
                .accessibilityLabel("下一首")
              }
              trackPicker(engine)
            }
          }

          // 选歌
          VStack(alignment: .leading, spacing: 10) {
            Text("挑一首").font(.headline.weight(.semibold))
            TextField("过滤曲库", text: $pickerQuery)
              .textFieldStyle(.roundedBorder)
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
                HStack(spacing: 12) {
                  ArtView(seed: song.displayTitle, size: 40)
                  VStack(alignment: .leading, spacing: 2) {
                    Text(song.displayTitle).foregroundStyle(.primary).lineLimit(1)
                    Text(song.displayArtist).font(.caption).foregroundStyle(.secondary)
                  }
                  Spacer()
                  if engine.songID == song.songID {
                    Image(systemName: "waveform").foregroundStyle(.tint)
                  }
                }
                .padding(.vertical, 6)
              }
              .buttonStyle(.plain)
            }
          }
          .padding(.horizontal, 4)
        }
        .padding(.horizontal, 16)
        .padding(.bottom, 100)
      }
      .onChange(of: engine.activeIndex) { _, idx in
        if let idx, let cue = engine.timeline?.cues[safe: idx] {
          withAnimation { proxy.scrollTo(cue.start_ms, anchor: .center) }
        }
      }
    }
  }

  private func trackPicker(_ engine: PlayerEngine) -> some View {
    HStack(spacing: 8) {
      trackChip("原唱", icon: "mic.fill", on: engine.track == .original) {
        Task { _ = await engine.setTrack(.original) }
      }
      trackChip("伴奏", icon: "music.note", on: engine.track == .accompaniment) {
        Task { _ = await engine.setTrack(.accompaniment) }
      }
    }
  }

  private func trackChip(_ title: String, icon: String, on: Bool, action: @escaping () -> Void) -> some View {
    Button(action: action) {
      Label(title, systemImage: icon)
        .font(.subheadline.weight(.semibold))
        .frame(maxWidth: .infinity)
        .padding(.vertical, 10)
        .background(on ? AnyShapeStyle(KTV.accent) : AnyShapeStyle(Color.secondary.opacity(0.15)),
                    in: Capsule())
        .foregroundStyle(on ? .white : .primary)
    }
    .buttonStyle(.plain)
    .disabled(!on && appState.player.detail?.hasInstrumental != true)
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
          .foregroundStyle(active ? Color.accentColor : Color.secondary)
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
          RoundedRectangle(cornerRadius: 12).fill(Color.accentColor.opacity(0.1))
        }
      }
      .animation(.easeInOut(duration: 0.25), value: active)
    }
    .buttonStyle(.plain)
  }
}

