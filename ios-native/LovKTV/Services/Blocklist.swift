import Foundation

/// 本机屏蔽列表：按服务器 origin 分组的歌曲 id 集合，存 UserDefaults。
@Observable
final class SongBlocklist {
  private(set) var byServer: [String: Set<String>] = [:]
  private let defaultsKey = "remote-blocked"

  init() {
    if let data = UserDefaults.standard.data(forKey: defaultsKey),
       let saved = try? JSONDecoder().decode([String: Set<String>].self, from: data) {
      byServer = saved
    }
  }

  func isBlocked(_ songID: String, server: URL) -> Bool {
    byServer[server.absoluteString]?.contains(songID) == true
  }

  func add(_ songID: String, server: URL) {
    var set = byServer[server.absoluteString] ?? []
    set.insert(songID)
    byServer[server.absoluteString] = set
    persist()
  }

  func clear() {
    byServer = [:]
    persist()
  }

  private func persist() {
    if let data = try? JSONEncoder().encode(byServer) {
      UserDefaults.standard.set(data, forKey: defaultsKey)
    }
  }
}
