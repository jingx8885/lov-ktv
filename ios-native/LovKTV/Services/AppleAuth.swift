import AuthenticationServices
import Foundation

/// Sign in with Apple：拿 identity token + 名字交后端。
@MainActor
final class AppleAuth: NSObject {
  private var continuation: CheckedContinuation<String, Error>?

  func signIn() async throws -> String {
    let provider = ASAuthorizationAppleIDProvider()
    let request = provider.createRequest()
    request.requestedScopes = [.fullName, .email]
    let controller = ASAuthorizationController(authorizationRequests: [request])
    controller.delegate = self
    controller.presentationContextProvider = self
    return try await withCheckedThrowingContinuation { cont in
      self.continuation = cont
      controller.performRequests()
    }
  }
}

extension AppleAuth: ASAuthorizationControllerDelegate {
  func authorizationController(controller: ASAuthorizationController,
                               didCompleteWithAuthorization authorization: ASAuthorization) {
    defer { continuation = nil }
    guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential,
          let data = credential.identityToken,
          let token = String(data: data, encoding: .utf8) else {
      continuation?.resume(throwing: NSError(domain: "AppleAuth", code: -1,
                                             userInfo: [NSLocalizedDescriptionKey: "没拿到 Apple 凭证"]))
      return
    }
    var name = [credential.fullName?.givenName, credential.fullName?.familyName]
      .compactMap { $0 }.joined()
    if name.isEmpty { name = credential.email ?? "" }
    continuation?.resume(returning: "\(token)|\(name)")
  }

  func authorizationController(controller: ASAuthorizationController,
                               didCompleteWithError error: Error) {
    defer { continuation = nil }
    continuation?.resume(throwing: error)
  }
}

extension AppleAuth: ASAuthorizationControllerPresentationContextProviding {
  func presentationAnchor(for controller: ASAuthorizationController) -> ASPresentationAnchor {
    UIApplication.shared.connectedScenes
      .compactMap { $0 as? UIWindowScene }
      .flatMap { $0.windows }
      .first { $0.isKeyWindow } ?? ASPresentationAnchor()
  }
}
