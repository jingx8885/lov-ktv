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

  // MARK: - 在线搜歌（GET /api/search）

  var onlineQuery = "" { didSet { scheduleOnlineSearch() } }
  var hits: [SearchHit] = []
  var onlinePage = 1
  var onlineHasMore = false
  var searchingOnline = false
  var onlineError: String?
  private var onlineTask: Task<Void, Never>?
  private var onlineGeneration = 0

  func scheduleOnlineSearch() {
    onlineTask?.cancel()
    onlineTask = Task { [weak self] in
      try? await Task.sleep(for: .milliseconds(400))
      guard !Task.isCancelled else { return }
      await self?.searchOnline(page: 1)
    }
  }

  func searchOnline(page: Int) async {
    let q = onlineQuery.trimmingCharacters(in: .whitespaces)
    guard !q.isEmpty, let client else {
      hits = []; onlineHasMore = false; return
    }
    onlinePage = page
    searchingOnline = true
    defer { searchingOnline = false }
    onlineGeneration += 1
    let gen = onlineGeneration
    do {
      let result = try await client.search(query: q, page: page)
      guard gen == onlineGeneration else { return }
      hits = result.hits
      onlineHasMore = result.has_more
      onlineError = nil
    } catch {
      guard gen == onlineGeneration else { return }
      hits = []
      onlineHasMore = false
      onlineError = error.localizedDescription
      print("[library] online search failed:", error)
    }
  }

  func loadMoreOnline() async {
    guard onlineHasMore, let client else { return }
    let next = onlinePage + 1
    searchingOnline = true
    defer { searchingOnline = false }
    do {
      let result = try await client.search(
        query: onlineQuery.trimmingCharacters(in: .whitespaces), page: next)
      onlinePage = next
      hits += result.hits
      onlineHasMore = result.has_more
    } catch {}
  }
}
