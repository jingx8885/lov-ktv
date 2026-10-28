import AVFoundation
import Foundation
import os

/// 遥控接口请求路径白名单——与旧版 Capacitor RemotePlugin.allowed 完全对齐。
/// 只允许 GET /api/songs、GET/POST /api/rooms/{code}/... 与 POST /api/remote/reports。
enum APIWhitelist {
  static func allows(path: String, method: String) -> Bool {
    let pattern: String
    if method == "GET" {
      pattern = #"^/api/(songs(\?[^#]*|/[A-Za-z0-9_-]{1,100}(/learn/(campaign|lesson|mistakes|review|words))?)|search\?[^#]*|rooms/[A-Z0-9]{4,12})$"#
    } else {
      pattern = #"^/api/(rooms/[A-Z0-9]{4,12}/(queue|play|skip|mix|bump)|remote/reports|songs(/import|/[A-Za-z0-9_-]{1,100}/learn/(lesson|review|words/setup)))$"#
    }
    return (method == "GET" || method == "POST")
      && path.range(of: pattern, options: .regularExpression) != nil
  }
}

/// 官方服务把 /api/* 映射到 /api/remote/ios/* 并附带 Bearer key；
/// reports 特殊映射到 /api/remote/ios/reports。
enum RemotePath {
  static func map(_ path: String, official: Bool) -> String {
    guard official else { return path }
    if path == "/api/remote/reports" { return "/api/remote/ios/reports" }
    return "/api/remote/ios" + path.dropFirst(4)
  }
}

private final class NoRedirectDelegate: NSObject, URLSessionTaskDelegate, Sendable {
  func urlSession(_ session: URLSession, task: URLSessionTask,
                  willPerformHTTPRedirection response: HTTPURLResponse,
                  newRequest request: URLRequest,
                  completionHandler: @escaping @Sendable (URLRequest?) -> Void) {
    // 重定向不允许把配置好的服务器变成外部内容源
    completionHandler(nil)
  }
}

/// 对当前连接发起白名单内请求。actor 保证 session/凭据不可被并发改坏；
/// JSON 编解码在 actor 内（后台）完成，UI 拿到的都是值类型。
actor LovKTVClient {
  private let connection: Connection
  private let apiKey: String
  private let session: URLSession
  private let decoder = JSONDecoder()
  private let encoder = JSONEncoder()

  init(connection: Connection, apiKey: String = "") {
    self.connection = connection
    self.apiKey = apiKey
    let config = URLSessionConfiguration.ephemeral
    config.timeoutIntervalForRequest = 20
    config.timeoutIntervalForResource = 60
    config.httpCookieAcceptPolicy = .never
    config.httpShouldSetCookies = false
    if connection.mode == .selfHosted {
      // 自建服只许局域网地址，绕过系统代理直连（本机 Clash 会掐内网请求）
      config.connectionProxyDictionary = [:]
    }
    self.session = URLSession(configuration: config, delegate: NoRedirectDelegate(), delegateQueue: nil)
  }

  var baseURL: URL { connection.server }
  var isOfficial: Bool { connection.mode == .official }

  private func authorize(_ request: inout URLRequest) {
    request.setValue("ios", forHTTPHeaderField: "X-LovKTV-Platform")
    if connection.mode == .official, !apiKey.isEmpty {
      request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
    }
  }

  /// 发送 JSON 请求并解码响应。`path` 必须是白名单内的 /api/... 路径。
  private func send<T: Decodable & Sendable>(path: String, body: [String: Encodable]? = nil,
                                           as type: T.Type) async throws -> T {
    guard APIWhitelist.allows(path: path, method: body == nil ? "GET" : "POST") else {
      throw APIError.http(0, "请求不在遥控接口白名单内")
    }
    let mapped = RemotePath.map(path, official: connection.mode == .official)
    guard let url = URL(string: mapped, relativeTo: connection.server) else {
      throw APIError.http(0, "服务器地址无效")
    }
    let method = body == nil ? "GET" : "POST"
    var request = URLRequest(url: url)
    authorize(&request)
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    if let body {
      request.httpMethod = "POST"
      request.httpBody = try JSONSerialization.data(withJSONObject: body)
    }

    let data: Data
    let response: URLResponse
    do {
      (data, response) = try await session.data(for: request)
    } catch {
      NSLog("[client] %@ %@ -> %@", method, url.absoluteString, error.localizedDescription)
      throw APIError.network
    }
    guard data.count <= 4_000_000,
          let http = response as? HTTPURLResponse else { throw APIError.network }
    if http.statusCode == 401 || http.statusCode == 403 {
      throw connection.mode == .official ? APIError.invalidKey : APIError.http(http.statusCode, "")
    }
    if http.statusCode == 402 { throw APIError.serverRejected }
    guard (200..<300).contains(http.statusCode) else {
      let detail = (try? decoder.decode([String: String].self, from: data))?["detail"] ?? ""
      throw APIError.http(http.statusCode, detail)
    }
    if T.self == Empty.self { return Empty() as! T }
    do {
      return try decoder.decode(T.self, from: data)
    } catch {
      throw APIError.http(http.statusCode, "响应解析失败")
    }
  }

  struct Empty: Decodable, Sendable {}

  // MARK: - API surface（与网页遥控端一一对应）

  func songs(query: String, page: Int, count: Int = 20) async throws -> SongsPage {
    let items = [URLQueryItem(name: "q", value: query),
                 URLQueryItem(name: "page", value: String(page)),
                 URLQueryItem(name: "count", value: String(count))]
    var components = URLComponents(string: "/api/songs")!
    components.queryItems = items
    return try await send(path: components.string!, as: SongsPage.self)
  }

  func room() async throws -> RoomSnapshot {
    try await send(path: "/api/rooms/\(connection.room)", as: RoomSnapshot.self)
  }

  func enqueue(songID: String) async throws -> RoomSnapshot {
    try await send(path: "/api/rooms/\(connection.room)/queue",
                   body: ["song_id": songID], as: RoomSnapshot.self)
  }

  func play(paused: Bool) async throws -> RoomSnapshot {
    try await send(path: "/api/rooms/\(connection.room)/mix",
                   body: ["paused": paused], as: RoomSnapshot.self)
  }

  func setVolume(_ volume: Int) async throws -> RoomSnapshot {
    try await send(path: "/api/rooms/\(connection.room)/mix",
                   body: ["volume": volume], as: RoomSnapshot.self)
  }

  func skip() async throws -> RoomSnapshot {
    try await send(path: "/api/rooms/\(connection.room)/skip",
                   body: [:], as: RoomSnapshot.self)
  }

  /// 队列里“唱这首”：POST /play {id}。itemID 是队列条目 id（不是 song_id）。
  func playItem(_ itemID: String) async throws -> RoomSnapshot {
    try await send(path: "/api/rooms/\(connection.room)/play",
                   body: ["id": itemID], as: RoomSnapshot.self)
  }

  /// 置顶到待唱第一位：POST /bump {id}
  func bumpItem(_ itemID: String) async throws -> RoomSnapshot {
    try await send(path: "/api/rooms/\(connection.room)/bump",
                   body: ["id": itemID], as: RoomSnapshot.self)
  }

  /// 房间混音/显示设置：vocal_mix 0..1、mic_gain 0..100、
  /// lyric_mode ja|zh|roma|all、lyric_size 10..250、display_mode lyrics|mv
  func setMix(vocalMix: Double? = nil, micGain: Int? = nil,
              lyricMode: String? = nil, lyricSize: Int? = nil,
              displayMode: String? = nil) async throws -> RoomSnapshot {
    var body: [String: Encodable] = [:]
    if let vocalMix { body["vocal_mix"] = vocalMix }
    if let micGain { body["mic_gain"] = micGain }
    if let lyricMode { body["lyric_mode"] = lyricMode }
    if let lyricSize { body["lyric_size"] = lyricSize }
    if let displayMode { body["display_mode"] = displayMode }
    return try await send(path: "/api/rooms/\(connection.room)/mix",
                          body: body, as: RoomSnapshot.self)
  }

  // MARK: - 在线搜歌 / 学习 / 歌曲详情

  func search(query: String, page: Int = 1, count: Int = 10) async throws -> SearchResponse {
    var components = URLComponents(string: "/api/search")!
    components.queryItems = [
      URLQueryItem(name: "q", value: query),
      URLQueryItem(name: "page", value: String(page)),
      URLQueryItem(name: "count", value: String(count)),
    ]
    return try await send(path: components.string!, as: SearchResponse.self)
  }

  func importHit(_ hit: SearchHit) async throws -> Song {
    try await send(path: "/api/songs/import", body: [
      "id": hit.id,
      "query": hit.displayTitle,
      "title": hit.displayTitle,
      "artist": hit.displayArtist == "未知歌手" ? "" : hit.displayArtist,
    ], as: Song.self)
  }

  /// 歌曲详情（含 files[] 判断有无 instrumental.wav）
  func songDetail(_ id: String) async throws -> SongDetail {
    try await send(path: "/api/songs/\(id)", as: SongDetail.self)
  }

  func learnCampaign(_ songID: String) async throws -> LearnCampaign {
    try await send(path: "/api/songs/\(songID)/learn/campaign", as: LearnCampaign.self)
  }

  func learnLesson(_ songID: String, unit: String, skill: String) async throws -> Lesson {
    var components = URLComponents(string: "/api/songs/\(songID)/learn/lesson")!
    components.queryItems = [
      URLQueryItem(name: "unit", value: unit),
      URLQueryItem(name: "skill", value: skill),
    ]
    return try await send(path: components.string!, as: Lesson.self)
  }

  func learnReview(_ songID: String) async throws -> Lesson {
    try await send(path: "/api/songs/\(songID)/learn/review", as: Lesson.self)
  }

  /// 提交课程结果。非 play_mode 技能必须带 attempt_id 与逐题 answers。
  func submitLesson(_ songID: String, unit: String, skill: String,
                    attemptID: String, pct: Int,
                    answers: [[String: AnyEncodable]]?) async throws -> LessonResult {
    var body: [String: Encodable] = [
      "unit_id": unit, "skill": skill, "attempt_id": attemptID, "pct": pct,
    ]
    if let answers {
      body["answers"] = answers
    }
    return try await send(path: "/api/songs/\(songID)/learn/lesson",
                          body: body, as: LessonResult.self)
  }

  // MARK: - 媒体资源（不在 JSON 白名单，直接构造 URL）

  /// /media/{id}/{name} 的完整 URL；官方服走 /api/remote/ios/media/{id}（仅 original.mp3）。
  func mediaURL(songID: String, name: String) -> URL? {
    guard songID.range(of: #"^[A-Za-z0-9_-]{1,100}$"#, options: .regularExpression) != nil else { return nil }
    let path = connection.mode == .official
      ? "/api/remote/ios/media/\(songID)"
      : "/media/\(songID)/\(name)"
    return URL(string: path, relativeTo: connection.server)
  }

  /// 预览流地址 /api/preview/{id}（仅自建服可达）
  func previewURL(hitID: String) -> URL? {
    guard hitID.range(of: #"^[A-Za-z0-9_:-]{1,100}$"#, options: .regularExpression) != nil else { return nil }
    return URL(string: "/api/preview/\(hitID)", relativeTo: connection.server)
  }

  /// 下载歌词时间轴 JSON；不存在/未就绪返回 nil
  func fetchTimeline(songID: String) async -> LyricsTimeline? {
    guard let url = mediaURL(songID: songID, name: "lyrics.json") else { return nil }
    var request = URLRequest(url: url)
    authorize(&request)
    guard let (data, response) = try? await session.data(for: request),
          let http = response as? HTTPURLResponse, http.statusCode == 200 else { return nil }
    return try? decoder.decode(LyricsTimeline.self, from: data)
  }

  /// AVURLAsset 可用的授权请求（官方服需要 Bearer 头）
  func authorizedAsset(url: URL) -> AVURLAsset {
    var headers: [String: String] = ["X-LovKTV-Platform": "ios"]
    if connection.mode == .official, !apiKey.isEmpty {
      headers["Authorization"] = "Bearer \(apiKey)"
    }
    return AVURLAsset(url: url, options: ["AVURLAssetHTTPHeaderFieldsKey": headers])
  }

  /// 房间实时快照推送。返回每个 snapshot 的 AsyncStream；连接断开即结束。
  /// URLSession WebSocket 不支持官方服的 Bearer 以外的签名要求，白名单外不走这里。
  func roomSocket() -> URLSessionWebSocketTask? {
    guard var components = URLComponents(url: connection.server, resolvingAgainstBaseURL: true) else { return nil }
    components.scheme = connection.server.scheme == "https" ? "wss" : "ws"
    components.path = (connection.mode == .official ? "/api/remote/ios" : "") + "/ws/rooms/\(connection.room)"
    guard let url = components.url else { return nil }
    var request = URLRequest(url: url)
    authorize(&request)
    return session.webSocketTask(with: request)
  }

  func report(songID: String, reason: String) async throws {
    let _: Empty = try await send(path: "/api/remote/reports",
                                  body: ["song_id": songID, "reason": reason],
                                  as: Empty.self)
  }

  /// 手机试听：自建服走 /media/{id}/original.mp3，官方走 /api/remote/ios/media/{id}。
  /// 大小上限 30MB，拒绝重定向；返回本地文件 URL（调用方负责删除）。
  func downloadPreview(songID: String) async throws -> URL {
    guard songID.range(of: #"^[A-Za-z0-9_-]{1,100}$"#, options: .regularExpression) != nil else {
      throw APIError.http(0, "歌曲 ID 无效")
    }
    let suffix = connection.mode == .official
      ? "/api/remote/ios/media/\(songID)"
      : "/media/\(songID)/original.mp3"
    guard let url = URL(string: suffix, relativeTo: connection.server) else {
      throw APIError.http(0, "服务器地址无效")
    }
    var request = URLRequest(url: url)
    authorize(&request)
    let (file, response): (URL, URLResponse)
    do {
      (file, response) = try await session.download(for: request)
    } catch {
      throw APIError.network
    }
    guard let http = response as? HTTPURLResponse else { throw APIError.network }
    if connection.mode == .official && [401, 403].contains(http.statusCode) {
      throw APIError.invalidKey
    }
    guard http.statusCode == 200 else { throw APIError.http(http.statusCode, "试听不可用") }
    let size = (try? file.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
    guard size > 0, size <= 30_000_000 else { throw APIError.http(0, "音频超过 30 MB 或为空") }
    return file
  }
}

/// 异构 JSON 值包装器（answers 里 int/string/array 混着来）
struct AnyEncodable: Encodable, @unchecked Sendable {
  private let value: Any
  init(_ value: Any) { self.value = value }
  func encode(to encoder: Encoder) throws {
    var container = encoder.singleValueContainer()
    switch value {
    case let v as String: try container.encode(v)
    case let v as Int: try container.encode(v)
    case let v as Double: try container.encode(v)
    case let v as Bool: try container.encode(v)
    case let v as [AnyEncodable]: try container.encode(v)
    case let v as [Int]: try container.encode(v)
    case let v as [String: AnyEncodable]: try container.encode(v)
    default: try container.encodeNil()
    }
  }
}
