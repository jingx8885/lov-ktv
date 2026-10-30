import Foundation
import Security

/// 官方服务 API key 存 Keychain（本机不导出），与旧 Capacitor 端同一服务/账户名。
enum KeychainStore {
  private static var query: [String: Any] {
    [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: "com.lovktv.phone.official",
      kSecAttrAccount as String: "remote-api-key",
    ]
  }

  /// 官方端校验：lkr_ + 43 位 [A-Za-z0-9_-]
  static func isValidKey(_ key: String) -> Bool {
    key.range(of: #"^lkr_[A-Za-z0-9_-]{43}$"#, options: .regularExpression) != nil
  }

  static func read() -> String? {
    var query = self.query
    query[kSecReturnData as String] = true
    query[kSecMatchLimit as String] = kSecMatchLimitOne
    var result: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    guard status == errSecSuccess,
          let data = result as? Data,
          let key = String(data: data, encoding: .utf8), !key.isEmpty else { return nil }
    return key
  }

  @discardableResult
  static func write(_ key: String) -> Bool {
    let attributes: [String: Any] = [
      kSecValueData as String: Data(key.utf8),
      kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
    ]
    let status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
    if status == errSecItemNotFound {
      var item = query
      item.merge(attributes) { _, new in new }
      return SecItemAdd(item as CFDictionary, nil) == errSecSuccess
    }
    return status == errSecSuccess
  }

  /// 官方接入调试注入：跳过 UI，直接写 key 到 Keychain。
  /// 调用方只拿真 key 调一次，不留在代码里。
  static func injectOfficialKey(_ key: String) {
    _ = write(key)
  }

  static func clear() {
    let status = SecItemDelete(query as CFDictionary)
    assert(status == errSecSuccess || status == errSecItemNotFound)
  }
}
