import Foundation

/// 房间快照：正在播放 + 待唱队列 + 播放/音量状态。
struct RoomSnapshot: Decodable, Sendable {
  var code: String?
  var paused: Bool
  var volume: Double?
  var now_playing: Song?
  var queue: [Song]
  var now_index: Int?
  var vocal_mix: Double?
  var mic_gain: Double?
  var lyric_mode: String?
  var lyric_size: Int?
  var display_mode: String?

  var queueCount: Int { queue.count }
  /// 网页端规则：只有排在正在播放之后第二位及以后的才显示“置顶”
  func canBump(at index: Int) -> Bool {
    index > (now_index ?? 0) + 1
  }
}

/// WebSocket 推送包：{"type":"snapshot","room":{...}}
struct RoomPush: Decodable, Sendable {
  var type: String
  var room: RoomSnapshot
}
