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

  // 账号
  var user: UserProfile?
  var authStatus: AuthStatus?
  var googleConfig: GoogleConfig?

  // 房间
  var room: RoomSnapshot?

  // 试听（下载后播，自建/官方通用）
  let preview = PreviewPlayer()
  // 在线搜试听流 + 听歌播放器
  let stream = StreamPreview()
  let player = PlayerEngine()

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
      // 恢复本连接下缓存的会话 cookie 与用户信息
      if let cookie = SessionStore.read(for: saved.server) {
        Task { await client?.setSessionCookie(cookie) }
      }
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
      // 本连接下如果有旧的会话 cookie 先带着；首次 authMe 再刷新
      if let savedCookie = SessionStore.read(for: candidate.server) {
        await newClient.setSessionCookie(savedCookie)
      }
      Task { await refreshAuth() }
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
    stream.stop()
    player.stop()
    user = nil
    authStatus = nil
    googleConfig = nil
    connection = nil
    client = nil
    room = nil
    blocklist.clear()
    if let connection { SessionStore.clear(for: connection.server) }
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

  /// 队列里“唱这首”
  func playItem(_ itemID: String) async {
    guard let client else { return }
    await run { self.room = try await client.playItem(itemID) }
  }

  /// 置顶到待唱第一位
  func bumpItem(_ itemID: String) async {
    guard let client else { return }
    await run { self.room = try await client.bumpItem(itemID) }
  }

  /// 房间混音/显示设置（人声开关、歌词模式/字号、显示模式）
  func setMix(vocalMix: Double? = nil,
              lyricMode: String? = nil, lyricSize: Int? = nil,
              displayMode: String? = nil) async {
    guard let client else { return }
    await run {
      self.room = try await client.setMix(
        vocalMix: vocalMix, lyricMode: lyricMode,
        lyricSize: lyricSize, displayMode: displayMode)
    }
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

  /// 官方接入：浏览器登录后跳回 app 拿到 key，或直接注入（开发联调）。
  /// 流程：app 点"一键接入官方" → Safari 打开 auth/qr → 登录确认 →
  /// 后端 302 到 lovktv://official?ticket=xxx&key=yyy → app 接住注入。
  func startOfficialConnect(roomCode: String) async -> String? {
    guard let client else { return "请先连接服务器" }
    do {
      // 登录完成后后端 302 回跳 app：lovktv://official?key=...&room=...
      let deep = "lovktv://official?room=\(roomCode)"
      let ticket = try await client.authQR(room: roomCode, next: deep)
      let url = URL(string: ticket.url)!
      await UIApplication.shared.open(url)
      return nil
    } catch { return error.localizedDescription }
  }

  /// 深链入口：lovktv://official?key=lkr_...&room=CODE
  /// （浏览器确认后回来，与轮询 claim 是双保险，谁先到谁注入。）
  func handleDeepLink(_ url: URL) async -> String? {
    guard url.scheme == "lovktv", url.host == "official" else { return nil }
    let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
    let key = items.first(where: { $0.name == "key" })?.value ?? ""
    let room = items.first(where: { $0.name == "room" })?.value ?? ""
    guard !key.isEmpty else { return "链接里没有 API key" }
    return await officialInject(apiKey: key, roomCode: room)
  }

  /// 扫码接入：认到 ?ticket= 直接 claim，member 拿 api_key 注入；
  /// 非 member 用户拿不到 key 但也会立会话（浏览器端是同一账号）。
  func claimTicket(_ ticket: String, roomCode: String) async -> String? {
    guard let client else { return "请先连接服务器" }
    do {
      let claim = try await client.authQRClaim(
        ticket: ticket, next: "lovktv://official?room=\(roomCode)")
      if let key = claim.api_key, !key.isEmpty {
        _ = await officialInject(apiKey: key, roomCode: roomCode)
        return nil
      }
      if claim.user != nil {
        await refreshAuth()
        return "已确认登录，但该账号没有 member API key"
      }
      return "二维码还没在浏览器里确认"
    } catch { return error.localizedDescription }
  }

  /// 官方接入调试：直接注入 API key + 房间码，跳过设置页表单。
  /// 仅开发用；生产别走这条路。
  func officialInject(apiKey: String, roomCode: String) async -> String? {
    guard let connection = try? ConnectionValidator.parse(
      ConnectionValidator.officialOrigin.absoluteString, room: roomCode) else {
      return "房间码无效"
    }
    let newClient = LovKTVClient(connection: connection, apiKey: apiKey)
    do {
      let snapshot = try await newClient.room()
      preview.stop()
      apply(connection: connection, client: newClient)
      room = snapshot
      persist()
      apiKeyValid = true
      // 官方 key 也落 Keychain，下次 connect 走正常链路
      if connection.mode == .official { _ = KeychainStore.write(apiKey) }
      Task { await refreshAuth() }
      return nil
    } catch {
      return error.localizedDescription
    }
  }

  // MARK: - 账号

  func refreshAuth() async {
    guard let client else { return }
    do {
      let me = try await client.authMe()
      user = me.user
      authStatus = try? await client.authStatus()
      googleConfig = try? await client.googleConfig()
    } catch {
      user = nil
    }
  }

  func loginPassword(username: String, password: String) async -> String? {
    guard let client else { return "请先连接服务器" }
    do {
      let me = try await client.loginPassword(username: username, password: password)
      user = me.user
      await persistSession()
      return nil
    } catch { return error.localizedDescription }
  }

  func registerPassword(username: String, password: String) async -> String? {
    guard let client else { return "请先连接服务器" }
    do {
      let me = try await client.registerPassword(username: username, password: password)
      user = me.user
      await persistSession()
      return nil
    } catch { return error.localizedDescription }
  }

  func loginApple(identityToken: String, name: String) async -> String? {
    guard let client else { return "请先连接服务器" }
    do {
      let me = try await client.loginApple(identityToken: identityToken, name: name)
      user = me.user
      await persistSession()
      return nil
    } catch { return error.localizedDescription }
  }

  func loginGoogle(idToken: String) async -> String? {
    guard let client else { return "请先连接服务器" }
    do {
      let me = try await client.loginGoogle(idToken: idToken)
      user = me.user
      await persistSession()
      return nil
    } catch { return error.localizedDescription }
  }

  func logout() async {
    guard let client else { return }
    try? await client.logout()
    if let connection { SessionStore.clear(for: connection.server) }
    user = nil
  }

  private func persistSession() async {
    guard let connection else { return }
    let cookie = await client?.sessionCookie ?? ""
    if !cookie.isEmpty { SessionStore.write(cookie, for: connection.server) }
  }

  private func apply(connection: Connection, client: LovKTVClient? = nil) {
    self.connection = connection
    self.client = client ?? LovKTVClient(
      connection: connection,
      apiKey: connection.mode == .official ? (KeychainStore.read() ?? "") : "")
  }

  /// WebSocket 实时快照：连上后在 DeskView 的 task 里跑，断线自动重连。
  /// 官方 ios_router 没暴露 /ws，连不上时退回 3s 轮询，两边都安全。
  func listenRoomSnapshots() async {
    guard let client else { return }
    while !Task.isCancelled, self.client != nil {
      guard let socket = await client.roomSocket() else { return }
      socket.resume()
      var connected = true
      defer { socket.cancel(with: .normalClosure, reason: nil) }
      while connected, !Task.isCancelled {
        do {
          let message = try await socket.receive()
          if case .string(let text) = message,
             let data = text.data(using: .utf8),
             let payload = try? JSONDecoder().decode(RoomPush.self, from: data),
             payload.type == "snapshot" {
            self.room = payload.room
          }
        } catch {
          connected = false
        }
      }
      // 断线等 5s 重连；轮询兜底仍在跑，不怕空窗
      try? await Task.sleep(for: .seconds(5))
    }
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
