import SwiftUI

/// 遥控页：正在播放 + 播放/切歌/音量 + 待唱队列，3s 轮询刷新（对齐网页端）。
struct RemoteView: View {
  @Environment(AppState.self) private var appState
  var onGoSettings: () -> Void
  @State private var confirmSkip = false
  @State private var showMix = false

  var body: some View {
    NavigationStack {
      ZStack {
        KTVBackground()
        Group {
          if appState.connection == nil {
            NotConnectedView(onConnect: onGoSettings)
          } else {
            content
          }
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

  @ViewBuilder
  private var content: some View {
    ScrollView {
      VStack(spacing: 16) {
        nowCard
        transportCard
        queueCard
      }
      .padding(.horizontal, 16)
      .padding(.top, 8)
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

  // MARK: - 正在播放

  private var nowCard: some View {
    GlassCard {
      VStack(spacing: 14) {
        if let song = appState.room?.now_playing, !appState.isHidden(song) {
          GlowArtView(seed: song.displayTitle, size: 140)
            .padding(.top, 4)
          VStack(spacing: 6) {
            HStack(spacing: 8) {
              NeonTag(text: appState.room?.paused == true ? "已暂停" : "正在播放",
                      color: appState.room?.paused == true ? .orange : KTV.lime)
              NeonTag(text: "房间 \(appState.connection?.room ?? "")", color: KTV.cyan)
            }
            Text(song.displayTitle)
              .font(.title3.weight(.bold))
            Text(song.displayArtist)
              .font(.subheadline)
              .foregroundStyle(.secondary)
          }
        } else {
          GlowArtView(seed: "♪", size: 140).opacity(0.4)
          VStack(spacing: 6) {
            NeonTag(text: "空闲", color: KTV.cyan)
            Text("暂无播放").font(.title3.weight(.bold))
            Text("去曲库点一首歌吧").font(.subheadline).foregroundStyle(.secondary)
          }
        }
      }
      .frame(maxWidth: .infinity)
    }
  }

  // MARK: - 播控

  private var transportCard: some View {
    GlassCard {
      VStack(spacing: 18) {
        HStack(spacing: 36) {
          BigRoundButton(
            icon: appState.room?.paused == true ? "play.fill" : "pause.fill",
            tint: .white, size: 68) {
            Task { await appState.togglePlay() }
          }
          .disabled(appState.room?.now_playing == nil)
          .accessibilityLabel(appState.room?.paused == true ? "继续播放" : "暂停播放")

          BigRoundButton(icon: "forward.fill", tint: KTV.cyan, size: 68) {
            confirmSkip = true
          }
          .accessibilityLabel("下一首")
        }
        VolumeRow(volume: appState.room?.volume ?? 70) { value in
          Task { await appState.setVolume(value) }
        }
      }
      .frame(maxWidth: .infinity)
    }
  }

  // MARK: - 队列

  private var queueCard: some View {
    GlassCard(padding: 8) {
      VStack(alignment: .leading, spacing: 0) {
        HStack {
          Text("待唱队列").font(.subheadline.weight(.semibold))
          Spacer()
          if !appState.visibleQueue.isEmpty {
            NeonTag(text: "\(appState.visibleQueue.count)", color: KTV.pink)
          }
        }
        .padding(.horizontal, 8).padding(.top, 8).padding(.bottom, 4)

        if appState.visibleQueue.isEmpty {
          Text("队列空空的，去曲库点首歌吧")
            .font(.subheadline).foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, alignment: .center)
            .padding(.vertical, 20)
        } else {
          ForEach(Array(appState.visibleQueue.enumerated()), id: \.element.queueItemID) { index, song in
            QueueItemRow(
              song: song,
              isNowPlaying: index == (appState.room?.now_index ?? 0),
              canBump: appState.room?.canBump(at: index) == true,
              onPlay: { Task { await appState.playItem(song.queueItemID) } },
              onBump: { Task { await appState.bumpItem(song.queueItemID) } })
          }
        }
      }
    }
  }
}

/// 队列条目行
private struct QueueItemRow: View {
  let song: Song
  let isNowPlaying: Bool
  let canBump: Bool
  let onPlay: () -> Void
  let onBump: () -> Void

  var body: some View {
    HStack(spacing: 12) {
      ArtView(seed: song.displayTitle, size: 40)
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
            .font(.caption)
            .foregroundStyle(.secondary)
            .lineLimit(1)
        }
      }
      Spacer(minLength: 8)
      Button("唱这首", action: onPlay)
        .buttonStyle(.bordered)
        .buttonBorderShape(.capsule)
        .tint(.accentColor)
        .disabled(isNowPlaying)
      if canBump {
        Button(action: onBump) {
          Image(systemName: "arrow.up.to.line")
            .font(.body.weight(.semibold))
            .frame(width: 30, height: 30)
        }
        .buttonStyle(.plain)
        .foregroundStyle(.secondary)
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
