import Foundation

/// /api/auth/me 的对外投影
struct AuthMe: Decodable, Sendable {
  var user: UserProfile
  var song_admin: Bool?
  var quota: Quota?
  var points: Points?
}

struct UserProfile: Decodable, Sendable {
  var id: String
  var sid: String?
  var nickname: String?
  var avatar: String?
  var email: String?
  var plan: String?
  var plan_status: String?
  var plan_expires_at: Int?
  var username: String?
  var language: String?
  var account: Bool?
  var admin: Bool?
  var created_at: Int?

  var displayName: String {
    nickname?.isEmpty == false ? nickname! : (email ?? "未命名")
  }
  var providerTag: String {
    if account == true { return "账号" }
    return "游客"
  }
}

struct Quota: Decodable, Sendable {
  var limit: Int?
  var remaining: Int?
  var period: String?
}
struct Points: Decodable, Sendable { var total: Int? }

struct AuthStatus: Decodable, Sendable {
  var wechat: Bool?
  var wechat_quick: Bool?
  var qr: Bool?
  var password: Bool?
  var google: Bool?
  var guest_limit: Int?
  var lovbrowser: Bool?
}

struct GoogleConfig: Decodable, Sendable {
  var client_id: String?
  var enabled: Bool?
}

struct Playlist: Decodable, Sendable, Identifiable {
  var id: String
  var name: String
  var count: Int?
  var has_song: Int?
  var created_at: Int?
  var updated_at: Int?
}
