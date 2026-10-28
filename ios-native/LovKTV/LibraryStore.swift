import Foundation

/// 曲库页：防抖搜索 + 分页加载更多。
@MainActor
@Observable
final class LibraryStore {
  var query = "" { didSet { scheduleSearch() } }
  var songs: [Song] = []
  var total = 0
  var page = 1
  var searching = false
  private var generation = 0
  private var searchTask: Task<Void, Never>?

  var hasMore: Bool { songs.count < total }

  /// 输入防抖 400ms，对齐网页端行为
  private func scheduleSearch() {
    searchTask?.cancel()
    searchTask = Task { [weak self] in
      try? await Task.sleep(for: .milliseconds(400))
      guard !Task.isCancelled else { return }
      await self?.search(page: 1)
    }
  }

  func search(page: Int) async {
    searchTask?.cancel()
    self.page = page
    searching = true
    defer { searching = false }
    generation += 1
    let gen = generation
    // client 由视图注入；抽出来便于测试
    guard let client else { return }
    do {
      let result = try await client.songs(query: query, page: page)
      guard gen == generation else { return }
      songs = result.songs
      total = result.total
    } catch {
      guard gen == generation else { return }
      songs = []
      total = 0
    }
  }

  func loadMore() async {
    guard hasMore, let client else { return }
    let next = page + 1
    searching = true
    defer { searching = false }
    do {
      let result = try await client.songs(query: query, page: next)
      page = next
      songs += result.songs
      total = result.total
    } catch {
      // 保持现状，用户可再拉
    }
  }

  var client: LovKTVClient?
}
