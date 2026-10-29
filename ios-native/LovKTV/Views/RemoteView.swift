import SwiftUI

/// 遥控页：主唱台布局——顶部大封面舞台 → 播控浮条 → 待唱队列。
/// 竖向一屏到底，不堆卡片。
struct RemoteView: View {
  @Environment(AppState.self) private var appState
  var onGoSettings: () -> Void
  @State private var confirmSkip = false
  @State private var showMix = false

  var body: some View {
    NavigationStack {
      ZStack {
        KTVBackground()
        if appState.connection == nil {
          NotConnectedView(onConnect: onGoSettings)
        } else {
          stage
        }
      }
      .navigationTitle("遥控")
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
      .sheet(isPresented: $showMix) {
        RoomMixSheet()
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
  }

  // MARK: - 舞台

  private var stage: some View {
    ScrollView {
      VStack(spacing: 0) {
        stageHero
        transportBar
        queueSection
      }
      .padding(.bottom, 100)
    }
    .refreshable { _ = await appState.refresh() }
    .confirmationDialog("切换到下一首？当前歌曲会立即停止。", isPresented: $confirmSkip) {
      Button("下一首", role: .destructive) {
        Task { await appState.skip() }
      }
      Button("取消", role: .cancel) {}
    }
  }

  private var stageHero: some View {
    VStack(spacing: 18) {
      // 顶部氛围：大封面 + 状态胶囊 + 标题
      ZStack {
        GlowArtView(seed: appState.room?.now_playing?.displayTitle ?? "♪", size: 180)
          .padding(.top, 16)
          .opacity(appState.room?.now_playing == nil ? 0.35 : 1)
      }
      VStack(spacing: 8) {
        HStack(spacing: 8) {
          NeonTag(text: appState.room?.paused == true ? "已暂停" : "正在播放",
                  color: appState.room?.paused == true ? .orange : KTV.lime)
          NeonTag(text: "房间 \(appState.connection?.room ?? "")", color: KTV.cyan)
        }
        Text(appState.room?.now_playing?.displayTitle ?? "暂无播放")
          .font(.title2.weight(.bold))
          .lineLimit(1)
        Text(appState.room?.now_playing?.displayArtist ?? "去曲库点一首歌吧")
          .font(.subheadline)
          .foregroundStyle(.secondary)
      }
      VolumeRow(volume: appState.room?.volume ?? 70) { value in
        Task { await appState.setVolume(value) }
      }
      .padding(.horizontal, 8)
    }
    .padding(.horizontal, 20)
    .padding(.top, 8)
    .padding(.bottom, 18)
  }

  // MARK: - 播控浮条

  private var transportBar: some View {
    HStack(spacing: 0) {
      transportButton(icon: "speaker.slash.fill", label: "静音") {
        Task { await appState.setVolume(0) }
      }
      transportButton(
        icon: appState.room?.paused == true ? "play.fill" : "pause.fill",
        label: appState.room?.paused == true ? "继续" : "暂停",
        prominent: true) {
        Task { await appState.togglePlay() }
      }
      .disabled(appState.room?.now_playing == nil)
      transportButton(icon: "forward.fill", label: "下一首") {
        confirmSkip = true
      }
      transportButton(icon: "mic.fill", label: "麦克风") {
        showMix = true
      }
    }
    .frame(maxWidth: .infinity)
    .padding(.vertical, 10)
    .background {
      Capsule().fill(KTV.card.opacity(0.85))
        .overlay(Capsule().stroke(KTV.accent, lineWidth: 1))
        .shadow(radius: 12, y: 4)
    }
    .padding(.horizontal, 20)
    .padding(.vertical, 12)
  }

  private func transportButton(icon: String, label: String,
                               prominent: Bool = false, action: @escaping () -> Void) -> some View {
    Button(action: action) {
      VStack(spacing: 5) {
        Image(systemName: icon)
          .font(.system(size: prominent ? 22 : 18, weight: .semibold))
        Text(label)
          .font(.caption2.weight(.medium))
      }
      .frame(maxWidth: .infinity)
      .padding(.vertical, 8)
      .foregroundStyle(prominent ? Color.white : Color.white.opacity(0.8))
      .background {
        if prominent {
          Circle().fill(KTV.accent).frame(width: 52, height: 52)
            .shadow(color: KTV.pink.opacity(0.5), radius: 8)
        }
      }
    }
    .buttonStyle(.plain)
    .contentTransition(.symbolEffect(.replace))
  }

  // MARK: - 队列

  private var queueSection: some View {
    VStack(alignment: .leading, spacing: 10) {
      HStack {
        Text("待唱队列").font(.headline.weight(.semibold))
        if !appState.visibleQueue.isEmpty {
          NeonTag(text: "\(appState.visibleQueue.count)", color: KTV.pink)
        }
      }
      .padding(.horizontal, 20)

      if appState.visibleQueue.isEmpty {
        VStack(spacing: 14) {
          Image("EmptyArt")
            .resizable().aspectRatio(contentMode: .fit)
            .frame(width: 140)
          Text("队列空空的").font(.subheadline.weight(.medium))
          Text("去曲库点一首歌，它会出现在这里")
            .font(.caption).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 40)
      } else {
        VStack(spacing: 0) {
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
        .padding(.horizontal, 8)
        .background {
          RoundedRectangle(cornerRadius: 18).fill(KTV.card.opacity(0.6))
        }
        .padding(.horizontal, 16)
      }
    }
    .padding(.top, 8)
  }
}

/// 队列行：序号 + 封面 + 标题 + 状态 + 唱这首/置顶
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
        ArtView(seed: song.displayTitle, size: 44)
        if isNowPlaying {
          Circle().fill(KTV.lime).frame(width: 14, height: 14)
            .overlay(Circle().stroke(.white, lineWidth: 2))
            .offset(x: 16, y: 16)
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
      Button { onPlay() } label: {
        Image(systemName: "play.circle.fill")
          .font(.title2)
          .foregroundStyle(isNowPlaying ? Color.secondary : Color.accentColor)
      }
      .buttonStyle(.plain)
      .disabled(isNowPlaying)
      .accessibilityLabel("唱这首")
      if canBump {
        Button { onBump() } label: {
          Image(systemName: "arrow.up.to.line.circle.fill")
            .font(.title3)
            .foregroundStyle(.secondary)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("置顶")
      }
    }
    .padding(.horizontal, 12).padding(.vertical, 10)
    .background {
      if isNowPlaying {
        RoundedRectangle(cornerRadius: 12).fill(KTV.lime.opacity(0.08))
      }
    }
  }
}
