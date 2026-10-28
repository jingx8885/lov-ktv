import Foundation

enum APIError: LocalizedError {
  case network
  case invalidKey
  case serverRejected
  case http(Int, String)

  var errorDescription: String? {
    switch self {
    case .network: return "无法连接服务器，请检查地址、网络及局域网权限"
    case .invalidKey: return "API key 无效或已失效"
    case .serverRejected: return "服务器未允许点歌，请联系服务器管理员"
    case .http(let code, let detail):
      return detail.isEmpty ? "服务器请求失败（\(code)）" : detail
    }
  }
}
