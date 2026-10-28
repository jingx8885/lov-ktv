import Foundation

/// 在线搜歌结果：/api/search 的单条命中，各来源字段尽量对齐网页端
struct SearchHit: Decodable, Identifiable, Sendable {
  var id: String
  var title: String?
  var artist: String?
  var album: String?
  var pic: String?
  var source: String?
  var is_mv: Bool?
  var clean: Bool?
  var preview_url: String?
  var duration: Int?
  var duration_match: String?

  var displayTitle: String { (title ?? "").htmlDecoded.nilIfEmpty ?? "未命名" }
  var displayArtist: String { (artist ?? "").htmlDecoded.nilIfEmpty ?? "未知歌手" }
  var sourceLabel: String {
    switch source {
    case "mugen": return "Mugen"
    case "bilibili": return "B站"
    case "netease": return "网易"
    case "soundcloud": return "SC"
    case "youtube": return "YT"
    default: return source ?? ""
    }
  }
  var durationText: String {
    guard let duration, duration > 0 else { return "" }
    return String(format: "%d:%02d", duration / 60, duration % 60)
  }
}

struct SearchResponse: Decodable, Sendable {
  var query: String
  var page: Int
  var count: Int
  var has_more: Bool
  var hits: [SearchHit]
  var sources: [String]
}

extension String {
  /// 命中结果里常见 &amp; &lt; 等实体，展示前还原
  var htmlDecoded: String {
    var s = self
    let table = [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", "\""), ("&#39;", "'"), ("&apos;", "'"),
                 ("&nbsp;", " ")]
    for (k, v) in table { s = s.replacingOccurrences(of: k, with: v) }
    return s
  }
  var nilIfEmpty: String? { isEmpty ? nil : self }
}
