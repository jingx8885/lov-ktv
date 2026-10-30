import SwiftUI

/// 搜歌页：在线搜歌入库。入库后的管理与点歌在"点歌"tab 里完成，
/// 这一页保持单一的"搜 → 试听 → 入库"动线，对齐 m.html 的 search 页。
struct LibraryView: View {
  @Environment(AppState.self) private var appState
  @Environment(LibraryStore.self) private var library
  @State private var imported: Set<String> = []

  var body: some View {
    NavigationStack {
      ZStack {
        KTVBackground()
        if appState.connection == nil {
          ContentUnavailableView {
            Label("未连接", systemImage: "magnifyingglass")
          } description: {
            Text("先在设置里连接服务器，才能在线搜歌。")
          }
        } else {
          searchPane
        }
      }
      .navigationTitle("搜歌")
      .navigationBarTitleDisplayMode(.inline)
    }
  }

  private var searchPane: some View {
    VStack(spacing: 10) {
      SearchField(text: Bindable(library).onlineQuery, placeholder: "歌名 / 歌手")
        .padding(.horizontal, KTVLayout.margin)
        .padding(.top, 4)

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
            library.onlineQuery.isEmpty ? "搜歌名或歌手" : "没有搜到",
            systemImage: "globe",
            description: Text(library.onlineError
                              ?? (library.onlineQuery.isEmpty
                                  ? "先听再加入曲库；网易 / B站 / Mugen 等源的结果会出现在这里。"
                                  : "换个关键词试试。")))
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
        appState.showStatus("已开始导入，可在点歌台查看进度")
      } catch {
        imported.remove(hit.id)
        appState.showStatus(error.localizedDescription)
      }
    }
  }
}
