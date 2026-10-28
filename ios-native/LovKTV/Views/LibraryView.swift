import SwiftUI

/// 曲库页：搜索 + 分页加载；每行可点歌，更多菜单有试听/屏蔽/举报。
struct LibraryView: View {
  @Environment(AppState.self) private var appState
  @Environment(LibraryStore.self) private var library
  @Binding var listeningTitle: String?
  @State private var actionSong: Song?
  @State private var reportSong: Song?
  @State private var reportReason = ""
  @State private var enqueued: Set<String> = []

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
          list
        }
      }
      .navigationTitle("曲库")
      .searchable(text: Binding(get: { library.query }, set: { library.query = $0 }), placement: .navigationBarDrawer(displayMode: .always),
                  prompt: "歌名或歌手")
    }
    .task { await library.search(page: 1) }
  }

  @ViewBuilder
  private var list: some View {
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
        Button {
          Task { await library.loadMore() }
        } label: {
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
        Button("手机试听") { preview(song) }
      }
      Button("屏蔽", role: .destructive) {
        appState.block(song)
        actionSong = nil
      }
      Button("举报并屏蔽", role: .destructive) {
        reportSong = song
        actionSong = nil
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
        reportReason = ""
        reportSong = nil
      }
      Button("取消", role: .cancel) {
        reportReason = ""
        reportSong = nil
      }
    }
  }

  private func enqueue(_ song: Song) {
    enqueued.insert(song.songID)
    Task { await appState.enqueue(song: song) }
    Task {
      try? await Task.sleep(for: .milliseconds(1600))
      enqueued.remove(song.songID)
    }
  }

  private func preview(_ song: Song) {
    actionSong = nil
    listeningTitle = song.displayTitle
    Task {
      if let error = await appState.preview.play(song: song, client: appState.client) {
        listeningTitle = nil
        appState.showStatus(error)
      }
    }
  }
}
