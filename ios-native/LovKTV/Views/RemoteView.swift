import SwiftUI

/// 遥控页：正在播放 + 播放/切歌/音量 + 待唱队列，3s 轮询刷新（对齐网页端）。
struct RemoteView: View {
  @Environment(AppState.self) private var appState
  var onGoSettings: () -> Void
  @State private var confirmSkip = false
  @State private var showMix = false

  var body: some View {
    NavigationStack {
      Group {
        if appState.connection == nil {
          NotConnectedView(onConnect: onGoSettings)
        } else {
          content
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
      // 3 秒轮询兜底（WS 断开/官方服不支持时仍实时）
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
    List {
      nowPlaying
      controls
      queueSection
    }
    .listStyle(.insetGrouped)
    .refreshable { _ = await appState.refresh() }
    .confirmationDialog("切换到下一首？当前歌曲会立即停止。", isPresented: $confirmSkip) {
      Button("下一首", role: .destructive) {
        Task { await appState.skip() }
      }
      Button("取消", role: .cancel) {}
    }
  }

  private var nowPlaying: some View {
    Section {
      VStack(spacing: 14) {
        if let song = appState.room?.now_playing, !appState.isHidden(song) {
          ArtView(seed: song.displayTitle, size: 120)
            .padding(.top, 8)
          VStack(spacing: 4) {
            Text((appState.room?.paused == true ? "已暂停" : "正在播放")
              + " · 房间 \(appState.connection?.room ?? "")")
              .font(.caption.weight(.medium))
              .foregroundStyle(.secondary)
              .textCase(.uppercase)
            Text(song.displayTitle)
              .font(.title3.weight(.semibold))
            Text(song.displayArtist)
              .font(.subheadline)
              .foregroundStyle(.secondary)
          }
        } else {
          ArtView(seed: "♪", size: 120)
            .opacity(0.35)
            .padding(.top, 8)
          VStack(spacing: 4) {
            Text("空闲 · 房间 \(appState.connection?.room ?? "")")
              .font(.caption.weight(.medium))
              .foregroundStyle(.secondary)
            Text("暂无播放")
              .font(.title3.weight(.semibold))
            Text("去曲库点一首歌吧")
              .font(.subheadline)
              .foregroundStyle(.secondary)
          }
        }
      }
      .frame(maxWidth: .infinity)
      .padding(.vertical, 4)
    }
  }

  private var controls: some View {
    Section {
      HStack(spacing: 28) {
        Button { Task { await appState.togglePlay() } } label: {
          Image(systemName: (appState.room?.paused == true ? "play.fill" : "pause.fill"))
            .font(.title2)
            .frame(width: 56, height: 56)
            .background(.primary.opacity(0.08), in: Circle())
        }
        .disabled(appState.room?.now_playing == nil)
        .accessibilityLabel(appState.room?.paused == true ? "继续播放" : "暂停播放")

        Button { confirmSkip = true } label: {
          Image(systemName: "forward.fill")
            .font(.title2)
            .frame(width: 56, height: 56)
            .background(.primary.opacity(0.08), in: Circle())
        }
        .accessibilityLabel("下一首")
      }
      .frame(maxWidth: .infinity)
      .foregroundStyle(.primary)

      VolumeRow(volume: appState.room?.volume ?? 70) { value in
        Task { await appState.setVolume(value) }
      }
    }
  }

  private var queueSection: some View {
    Section {
      if appState.visibleQueue.isEmpty {
        Text("队列空空的，去曲库点首歌吧")
          .font(.subheadline)
          .foregroundStyle(.secondary)
          .frame(maxWidth: .infinity, alignment: .center)
          .padding(.vertical, 8)
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
    } header: {
      HStack {
        Text("待唱队列")
        if !appState.visibleQueue.isEmpty {
          Text("\(appState.visibleQueue.count)")
            .font(.caption.weight(.semibold))
            .foregroundStyle(.secondary)
        }
      }
    }
  }
}

private struct VolumeRow: View {
  let volume: Double
  let onCommit: (Double) -> Void
  @State private var editing = false
  @State private var draft: Double = 0

  var body: some View {
    HStack(spacing: 12) {
      Image(systemName: "speaker.fill").foregroundStyle(.secondary)
      Slider(value: Binding(
        get: { editing ? draft : volume },
        set: { draft = $0; editing = true }),
        in: 0...100, step: 1) { editing in
        if !editing { onCommit(draft); self.editing = false }
      }
      Image(systemName: "speaker.wave.3.fill").foregroundStyle(.secondary)
    }
    .accessibilityElement(children: .combine)
    .accessibilityLabel("音量")
    .accessibilityValue("\(Int(volume))")
  }
}

/// 队列条目行：封面 + 标题 + 状态 + 唱这首/置顶，对齐网页 desk 队列
private struct QueueItemRow: View {
  let song: Song
  let isNowPlaying: Bool
  let canBump: Bool
  let onPlay: () -> Void
  let onBump: () -> Void

  var body: some View {
    HStack(spacing: 12) {
      ArtView(seed: song.displayTitle)
      VStack(alignment: .leading, spacing: 3) {
        Text(song.displayTitle)
          .font(.body.weight(.medium))
          .lineLimit(1)
        HStack(spacing: 6) {
          if isNowPlaying {
            Text("正在唱")
              .font(.caption2.weight(.semibold))
              .padding(.horizontal, 6).padding(.vertical, 2)
              .background(Color.accentColor.opacity(0.18), in: Capsule())
              .foregroundStyle(.tint)
          } else if let badge = song.badge {
            Text(badge.text)
              .font(.caption2.weight(.semibold))
              .padding(.horizontal, 6).padding(.vertical, 2)
              .background(badge.isError ? Color.red.opacity(0.18) : Color.orange.opacity(0.18),
                          in: Capsule())
              .foregroundStyle(badge.isError ? .red : .orange)
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
    .padding(.horizontal, 14).padding(.vertical, 10)
  }
}
