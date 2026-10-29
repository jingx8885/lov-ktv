import Foundation

enum ConnectionMode: String, Codable, Sendable {
  case selfHosted = "self"
  case official
}

/// 连接配置：服务器根地址 + 房间码 + 连接方式，存 UserDefaults（API key 存 Keychain）。
struct Connection: Codable, Equatable, Sendable {
  var server: URL
  var room: String
  var mode: ConnectionMode
}

enum ConnectionError: LocalizedError {
  case invalidURL
  case insecureURL
  case unexpectedQuery
  case invalidRoom

  var errorDescription: String? {
    switch self {
    case .invalidURL: return "请输入 HTTPS 或局域网 HTTP 根地址"
    case .insecureURL: return "HTTP 只允许局域网地址，公网请用 HTTPS"
    case .unexpectedQuery: return "服务器地址只能带 ?room= 参数"
    case .invalidRoom: return "请输入 4-12 位字母数字房间码"
    }
  }
}

/// 与 ios/web/policy.js 的校验规则对齐：HTTPS 任意，HTTP 仅局域网；
/// 手动输入不允许 query；扫码可带 ?room=CODE（唯一允许的 query）。
enum ConnectionValidator {
  static let officialOrigin = URL(string: "https://ktv.lovbrowser.com")!

  static func isLocalHost(_ host: String) -> Bool {
    if host.hasSuffix(".local") || host == "localhost" || host == "127.0.0.1" || host == "::1" { return true }
    let parts = host.split(separator: ".").compactMap { Int($0) }
    return parts.count == 4 && parts.allSatisfy { (0...255).contains($0) }
      && (parts[0] == 10
        || (parts[0] == 192 && parts[1] == 168)
        || (parts[0] == 172 && (16...31).contains(parts[1])))
  }

  static func parse(_ raw: String, room roomFallback: String = "") throws -> Connection {
    guard let url = URL(string: raw.trimmingCharacters(in: .whitespacesAndNewlines)),
          let host = url.host?.lowercased(),
          url.user == nil, url.password == nil,
          ["http", "https"].contains(url.scheme ?? ""),
          url.scheme == "https" || isLocalHost(host)
    else {
      if let url = URL(string: raw.trimmingCharacters(in: .whitespacesAndNewlines)),
         url.scheme == "http", let host = url.host, !isLocalHost(host) {
        throw ConnectionError.insecureURL
      }
      throw ConnectionError.invalidURL
    }
    let path = url.path.isEmpty ? "/" : url.path
    guard ["/", "/m.html", "/tv.html"].contains(path) else { throw ConnectionError.invalidURL }

    var room = roomFallback
    if let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems {
      for item in items {
        guard item.name == "room" else { throw ConnectionError.unexpectedQuery }
        room = item.value ?? room
      }
    }
    room = room.trimmingCharacters(in: .whitespaces).uppercased()
    guard room.wholeMatch(of: /^[A-Z0-9]{4,12}$/) != nil else { throw ConnectionError.invalidRoom }

    var components = URLComponents(url: url, resolvingAgainstBaseURL: false)!
    components.query = nil
    components.path = "/"
    let server = components.url!
    let mode: ConnectionMode = host == officialOrigin.host ? .official : .selfHosted
    return Connection(server: server, room: room, mode: mode)
  }
}
