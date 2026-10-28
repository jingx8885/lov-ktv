import Foundation

/// 曲库条目。队列、搜索结果、正在播放共用这一个模型；
/// `id`/`song_id` 以服务器返回为准，展示与操作统一走 `songID`。
struct Song: Decodable, Identifiable, Sendable {
  var id: String?
  var song_id: String?
  var title: String?
  var artist: String?
  var status: String?
  var favorite: Bool?

  var songID: String { song_id ?? id ?? "" }
  var displayTitle: String { title?.isEmpty == false ? title! : "未命名" }
  var displayArtist: String { artist?.isEmpty == false ? artist! : "未知歌手" }
  var isReady: Bool { status == nil || status == "ready" }

  /// 处理中 / 失败徽标，与网页遥控端的展示规则一致。
  var badge: (text: String, isError: Bool)? {
    guard let status else { return nil }
    switch status {
    case "ready": return nil
    case "failed", "error": return ("处理失败", true)
    case "queued", "fetching", "separating", "aligning", "annotating", "running":
      return ("处理中", false)
    default: return nil
    }
  }
}

struct SongsPage: Decodable, Sendable {
  var songs: [Song]
  var total: Int
}
