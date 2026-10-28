import SwiftUI

/// 曲库页：入库列表 + 在线搜歌（分段切换）。
/// 在线搜只在已连接时出现——服务器没配 URL 根本到不了这里。
struct LibraryView: View {
  @Environment(AppState.self) private var appState
  @Environment(LibraryStore.self) private var library
  @Binding var listeningTitle: String?
  @State private var pane: Pane = .local
  @State private var actionSong: Song?
  @State private var reportSong: Song?
  @State private var reportReason = ""
  @State private var enqueued: Set<String> = []
  @State private var imported: Set<String> = []

  enum Pane: String, CaseIterable { case local = "入库", online = "在线搜" }

  var body: some View {
    NavigationStack {
      Group {
        if appState.connection == nil {
          ContentUnavailableView {
            Label("未连接", systemImage: "music.note.list")
          } description: {
            Text("先在设置里连接服务器，曲库会出现在这里。")
          }
        } else {
          content
        }
      }
      .navigationTitle("曲库")
      .searchable(text: Binding(get: { pane == .local ? library.query : library.onlineQuery },
                                set: { if pane == .local { library.query = $0 } else { library.onlineQuery = $0 } }),
                  placement: .navigationBarDrawer(displayMode: .always),
                  prompt: pane == .local ? "歌名或歌手" : "在线搜歌")
      .onChange(of: library.onlineQuery) { _, _ in if pane == .online { library.scheduleOnlineSearch() } }
    }
    .task(id: appState.connection) {
          library.client = appState.client
          await library.search(page: 1)
        }
  }

  @ViewBuilder
  private var content: some View {
    VStack(spacing: 0) {
      HStack(spacing: 8) {
        ForEach(Pane.allCases, id: \.self) { p in
          Button {
            pane = p
          } label: {
            Text(p.rawValue)
              .font(.subheadline.weight(.medium))
              .frame(maxWidth: .infinity)
              .padding(.vertical, 7)
              .background(pane == p ? Color.accentColor : Color.secondary.opacity(0.15),
                          in: RoundedRectangle(cornerRadius: 9))
              .foregroundStyle(pane == p ? .white : .primary)
          }
          .buttonStyle(.plain)
          .accessibilityLabel("切到\(p.rawValue)")
        }
      }
      .padding(.horizontal, 16).padding(.vertical, 8)
      if pane == .local { localList } else { onlineList }
    }
    .onChange(of: pane) { _, pane in
      if pane == .online {
        library.client = appState.client
        Task { await library.searchOnline(page: 1) }
      }
    }
  }

  // MARK: - 入库

  @ViewBuilder
  private var localList: some View {
    List {
      ForEach(library.songs.filter { !appState.isHidden($0) }) { song in
        SongRow(song: song, showsEnqueue: true,
                onEnqueue: { enqueue(song) },
                onMore: { actionSong = song },
                enqueued: enqueued.contains(song.songID))
      }
      if library.songs.isEmpty && !library.searching {
        ContentUnavailableView(
          library.query.isEmpty ? "暂无可显示的歌曲" : "没有找到相关歌曲",
          systemImage: "music.note.list",
          description: Text(library.query.isEmpty
                            ? "服务器曲库里还没有可唱的歌。" : "换个歌名或歌手试试。"))
        .listRowSeparator(.hidden)
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
    .refreshable { await library.search(page: 1) }
    .confirmationDialog(
      actionSong.map { "\($0.displayTitle) · \($0.displayArtist)" } ?? "",
      isPresented: .constant(actionSong != nil),
      titleVisibility: .visible,
      presenting: actionSong
    ) { song in
      if song.isReady {
        Button("手机试听") { previewLocal(song) }
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

  // MARK: - 在线搜

  @ViewBuilder
  private var onlineList: some View {
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
  }

  // MARK: - 动作

  private func enqueue(_ song: Song) {
    enqueued.insert(song.songID)
    Task { await appState.enqueue(song: song) }
    Task {
      try? await Task.sleep(for: .milliseconds(1600))
      enqueued.remove(song.songID)
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
        let song = try await client.importHit(hit)
        appState.showStatus("已开始导入，可在入库页查看进度")
        await library.search(page: 1)
        _ = song
      } catch {
        imported.remove(hit.id)
        appState.showStatus(error.localizedDescription)
      }
    }
  }
}

/// 在线搜结果行：封面(网络图或渐变) + 来源徽标 + 试听/入库
private struct OnlineHitRow: View {
  let hit: SearchHit
  let previewing: Bool
  let imported: Bool
  let onPreview: () -> Void
  let onImport: () -> Void

  var body: some View {
    HStack(spacing: 12) {
      cover
      VStack(alignment: .leading, spacing: 3) {
        Text(hit.displayTitle).font(.body.weight(.medium)).lineLimit(1)
        HStack(spacing: 6) {
          if !hit.sourceLabel.isEmpty {
            Text(hit.sourceLabel)
              .font(.caption2.weight(.semibold))
              .padding(.horizontal, 6).padding(.vertical, 2)
              .background(Color.accentColor.opacity(0.15), in: Capsule())
              .foregroundStyle(.tint)
          }
          if hit.is_mv == true {
            Text("MV")
              .font(.caption2.weight(.semibold))
              .padding(.horizontal, 6).padding(.vertical, 2)
              .background(Color.purple.opacity(0.15), in: Capsule())
              .foregroundStyle(.purple)
          }
          Text([hit.displayArtist, hit.durationText].filter { !$0.isEmpty }.joined(separator: " · "))
            .font(.caption).foregroundStyle(.secondary).lineLimit(1)
        }
      }
      Spacer(minLength: 8)
      Button { onPreview() } label: {
        Image(systemName: previewing ? "stop.circle.fill" : "play.circle.fill")
          .font(.title2)
      }
      .buttonStyle(.plain)
      .accessibilityLabel(previewing ? "停止试听" : "试听")
      Button(imported ? "已入库" : "入库") { onImport() }
        .buttonStyle(.borderedProminent)
        .buttonBorderShape(.capsule)
        .tint(imported ? .green : .accentColor)
        .disabled(imported)
    }
    .padding(.horizontal, 14).padding(.vertical, 10)
  }

  @ViewBuilder
  private var cover: some View {
    if let pic = hit.pic, let url = URL(string: pic) {
      AsyncImage(url: url) { phase in
        switch phase {
        case .success(let image):
          image.resizable().aspectRatio(contentMode: .fill)
        default:
          ArtView(seed: hit.displayTitle)
        }
      }
      .frame(width: 44, height: 44)
      .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    } else {
      ArtView(seed: hit.displayTitle)
    }
  }
}
