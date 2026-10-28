import Foundation
import SwiftUI

/// 全局状态：连接、客户端、房间快照、屏蔽列表、试听、Toast。
/// 视图只做展示与触发，异步逻辑都收在这里（State-as-Bridge：UI 直接改 var，网络走 actor client）。
@MainActor
@Observable
final class AppState {
  // 连接
  var connection: Connection?
  private(set) var client: LovKTVClient?
  var apiKeyValid = true

  // 房间
  var room: RoomSnapshot?

  // 试听
  let preview = PreviewPlayer()

  // 屏蔽
  let blocklist = SongBlocklist()

  // Toast
  var statusMessage: String?
  private var statusGeneration = 0

  private let configKey = "remote-config"

  init() {
    if let data = UserDefaults.standard.data(forKey: configKey),
       let saved = try? JSONDecoder().decode(Connection.self, from: data) {
      apply(connection: saved)
    }
  }

  // MARK: - 连接生命周期

  /// 校验表单并建立连接。官方服务的 API key 先验格式、成功后写 Keychain。
  /// 返回错误文案（nil 表示成功）。
  func connect(mode: ConnectionMode, serverRaw: String, roomCode: String, apiKey: String) async -> String? {
    let candidate: Connection
    do {
      if mode == .official {
        candidate = try ConnectionValidator.parse(
          ConnectionValidator.officialOrigin.absoluteString, room: roomCode)
      } else {
        candidate = try ConnectionValidator.parse(serverRaw, room: roomCode)
      }
    } catch {
      return error.localizedDescription
    }

    var key = ""
    if candidate.mode == .official {
      let supplied = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
      if !supplied.isEmpty {
        guard KeychainStore.isValidKey(supplied) else { return "API key 格式无效" }
        key = supplied
      } else if let saved = KeychainStore.read(), KeychainStore.isValidKey(saved) {
        key = saved
      } else {
        return "请输入 API key"
      }
    }

    let newClient = LovKTVClient(connection: candidate, apiKey: key)
    do {
      let snapshot = try await newClient.room()
      // 连接成功才持久化
      if !key.isEmpty { _ = KeychainStore.write(key) }
      preview.stop()
      apply(connection: candidate, client: newClient)
      room = snapshot
      apiKeyValid = true
      persist()
      showStatus(candidate.mode == .official ? "已连接官方服务" : "已连接自己的服务器")
      return nil
    } catch {
      if case APIError.invalidKey = error { apiKeyValid = false }
      return error.localizedDescription
    }
  }

  func disconnect() {
    preview.stop()
    connection = nil
    client = nil
    room = nil
    blocklist.clear()
    KeychainStore.clear()
    UserDefaults.standard.removeObject(forKey: configKey)
    showStatus("已清除本机数据")
  }

  // MARK: - 房间

  /// 失败时返回错误文案；断线类错误会清掉房间快照提示重连。
  @discardableResult
  func refresh() async -> String? {
    guard let client else { return nil }
    do {
      room = try await client.room()
      apiKeyValid = true
      return nil
    } catch {
      if case APIError.invalidKey = error {
        apiKeyValid = false
        return error.localizedDescription
      }
      return error.localizedDescription
    }
  }

  func togglePlay() async {
    guard let room, let client else { return }
    await run { self.room = try await client.play(paused: !room.paused) }
  }

  func skip() async {
    guard let client else { return }
    await run { self.room = try await client.skip() }
  }

  func setVolume(_ volume: Double) async {
    guard let client else { return }
    await run { self.room = try await client.setVolume(Int(volume.rounded())) }
  }

  func enqueue(song: Song) async {
    guard let client, song.isReady else { return }
    await run { self.room = try await client.enqueue(songID: song.songID) }
  }

  // MARK: - 屏蔽 / 举报

  func isHidden(_ song: Song) -> Bool {
    guard let connection else { return false }
    return blocklist.isBlocked(song.songID, server: connection.server)
  }

  var visibleQueue: [Song] {
    (room?.queue ?? []).filter { !isHidden($0) }
  }

  /// 屏蔽当前歌：若正在播放把房间里的显示换成占位
  func block(_ song: Song) {
    guard let connection else { return }
    blocklist.add(song.songID, server: connection.server)
    if preview.playingID == song.songID { preview.stop() }
    showStatus("已在此设备屏蔽该内容")
  }

  func reportAndBlock(_ song: Song, reason: String) async {
    guard let client, let connection else { return }
    do {
      try await client.report(songID: song.songID, reason: String(reason.prefix(500)))
      blocklist.add(song.songID, server: connection.server)
      if preview.playingID == song.songID { preview.stop() }
      showStatus("举报已送达服务器管理员，内容已在本机屏蔽")
    } catch {
      showStatus(error.localizedDescription)
    }
  }

  func clearBlocklist() {
    blocklist.clear()
    showStatus("已清除屏蔽列表")
  }

  // MARK: - Toast

  func showStatus(_ message: String) {
    statusGeneration += 1
    let generation = statusGeneration
    statusMessage = message
    Task {
      try? await Task.sleep(for: .seconds(2.8))
      if statusGeneration == generation {
        withAnimation { statusMessage = nil }
      }
    }
  }

  private func apply(connection: Connection, client: LovKTVClient? = nil) {
    self.connection = connection
    self.client = client ?? LovKTVClient(
      connection: connection,
      apiKey: connection.mode == .official ? (KeychainStore.read() ?? "") : "")
  }

  private func persist() {
    if let connection,
       let data = try? JSONEncoder().encode(connection) {
      UserDefaults.standard.set(data, forKey: configKey)
    }
  }

  private func run(_ work: () async throws -> Void) async {
    do {
      try await work()
    } catch {
      if case APIError.invalidKey = error { apiKeyValid = false }
      showStatus(error.localizedDescription)
    }
  }
}
