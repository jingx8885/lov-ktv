import Foundation

/// /media/{id}/lyrics.json 的精简模型：逐句 + 逐词时间轴，用于卡拉OK高亮
struct LyricsTimeline: Decodable, Sendable {
  var cues: [Cue]

  struct Cue: Decodable, Sendable, Identifiable {
    var id: Int { start_ms }
    var text: String?
    var surface: String?
    var zh: String?
    var translation: String?
    var romaji: String?
    var start_ms: Int
    var end_ms: Int
    var tokens: [Token]?

    var display: String { surface ?? text ?? "" }
    var sub: String? { translation ?? zh }
  }

  struct Token: Decodable, Sendable {
    var surface: String?
    var text: String?
    var reading: String?
    var start_ms: Int
    var end_ms: Int
    var display: String { surface ?? text ?? "" }
  }

  /// 当前毫秒所在 cue 的下标
  func activeIndex(at ms: Int) -> Int? {
    cues.firstIndex { ms >= $0.start_ms && ms < $0.end_ms }
      ?? (ms < (cues.first?.start_ms ?? 0) ? 0 : cues.last.map { _ in cues.count - 1 })
  }
}
