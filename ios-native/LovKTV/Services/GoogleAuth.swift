import Foundation
import UIKit
#if canImport(GoogleSignIn)
import GoogleSignIn
#endif

/// Google 登录：GIDSignIn 出 idToken，服务端拿 tokeninfo 校验 aud。
/// clientID 从后端 /api/auth/google/config 拿（= GOOGLE_CLIENT_ID，aud 也按它）。
@MainActor
final class GoogleAuth {
  func signIn(serverClientID: String, presenting: UIViewController) async throws -> String {
#if canImport(GoogleSignIn)
    guard let clientID = serverClientID.nilIfEmpty else {
      throw NSError(domain: "GoogleAuth", code: -1,
                    userInfo: [NSLocalizedDescriptionKey: "服务端未配置 Google 登录"])
    }
    let config = GIDConfiguration(clientID: clientID, serverClientID: clientID)
    GIDSignIn.sharedInstance.configuration = config
    let result = try await GIDSignIn.sharedInstance.signIn(withPresenting: presenting)
    guard let token = result.user.idToken?.tokenString else {
      throw NSError(domain: "GoogleAuth", code: -1,
                    userInfo: [NSLocalizedDescriptionKey: "没拿到 Google id_token"])
    }
    return token
#else
    throw NSError(domain: "GoogleAuth", code: -2,
                  userInfo: [NSLocalizedDescriptionKey: "缺少 GoogleSignIn SDK"])
#endif
  }

  /// 顶层拿到一个可 present 的 VC
  func presenter() -> UIViewController? {
    UIApplication.shared.connectedScenes
      .compactMap { $0 as? UIWindowScene }
      .flatMap { $0.windows }
      .first { $0.isKeyWindow }?
      .rootViewController?
      .topPresented()
  }
}

private extension UIViewController {
  func topPresented() -> UIViewController {
    var vc = self
    while let next = vc.presentedViewController { vc = next }
    return vc
  }
}
