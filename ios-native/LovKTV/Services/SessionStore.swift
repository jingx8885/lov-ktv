import Foundation

/// 每个服务器 origin 一份 lovktv_session，存 UserDefaults（不是密钥级别，
/// 清了就是退出登录）。
enum SessionStore {
  private static let prefix = "lovktv_session:"

  private static func key(_ server: URL) -> String {
    prefix + server.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
  }

  static func read(for server: URL) -> String? {
    UserDefaults.standard.string(forKey: key(server))
  }

  static func write(_ token: String, for server: URL) {
    UserDefaults.standard.set(token, forKey: key(server))
  }

  static func clear(for server: URL) {
    UserDefaults.standard.removeObject(forKey: key(server))
  }
}
