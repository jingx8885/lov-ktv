import Foundation

/// 房间快照：正在播放 + 待唱队列 + 播放/音量状态。
struct RoomSnapshot: Decodable, Sendable {
  var code: String?
  var paused: Bool
  var volume: Double?
  var now_playing: Song?
  var queue: [Song]

  var queueCount: Int { queue.count }
}
