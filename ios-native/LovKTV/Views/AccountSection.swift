import AuthenticationServices
import SwiftUI

/// 设置页"账号"区：游客态（登录入口）/ 已登录态（头像+退出）。
struct AccountSection: View {
  @Environment(AppState.self) private var appState
  @State private var showPasswordSheet = false
  @State private var busy = false
  @State private var authError: String?
  private let appleAuth = AppleAuth()
  private let googleAuth = GoogleAuth()

  var body: some View {
    Section("账号") {
      if let user = appState.user {
        loggedIn(user)
      } else {
        loggedOut
      }
      if let authError {
        Text(authError).font(.caption).foregroundStyle(.red)
      }
    }
    .sheet(isPresented: $showPasswordSheet) {
      PasswordSheet { error in
        authError = error
        if error == nil { showPasswordSheet = false }
      }
    }
  }

  @ViewBuilder
  private var loggedOut: some View {
    Text("游客 · 登录后配额/歌单/学习进度跨设备同步")
      .font(.caption).foregroundStyle(.secondary)
    SignInWithAppleButton(.signIn) { request in
      request.requestedScopes = [.fullName, .email]
    } onCompletion: { result in
      Task { await apple(result) }
    }
    .signInWithAppleButtonStyle(.white)
    .frame(height: 44)
    .disabled(busy)

    if appState.googleConfig?.enabled == true {
      Button {
        Task { await google() }
      } label: {
        HStack {
          Image(systemName: "globe")
          Text("使用 Google 登录")
        }
        .frame(maxWidth: .infinity)
      }
      .buttonStyle(.bordered)
      .disabled(busy)
    }

    Button {
      showPasswordSheet = true
    } label: {
      Label("用户名密码登录", systemImage: "person.badge.key")
    }
  }

  @ViewBuilder
  private func loggedIn(_ user: UserProfile) -> some View {
    HStack(spacing: 12) {
      ZStack {
        Circle().fill(Color.accentColor.opacity(0.2))
        Text(String(user.displayName.prefix(1)))
          .font(.title3.weight(.bold))
      }
      .frame(width: 44, height: 44)
      VStack(alignment: .leading, spacing: 2) {
        Text(user.displayName)
        Text([user.email, user.providerTag].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "))
          .font(.caption).foregroundStyle(.secondary)
      }
    }
    Button("退出登录", role: .destructive) {
      Task { await appState.logout() }
    }
  }

  private func apple(_ result: Result<ASAuthorization, Error>) async {
    switch result {
    case .success(let authorization):
      guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential,
            let data = credential.identityToken,
            let token = String(data: data, encoding: .utf8) else {
        authError = "没拿到 Apple 凭证"
        return
      }
      var name = [credential.fullName?.givenName, credential.fullName?.familyName]
        .compactMap { $0 }.joined()
      if name.isEmpty { name = credential.email ?? "" }
      busy = true
      defer { busy = false }
      if let error = await appState.loginApple(identityToken: token, name: name) {
        authError = error
      } else {
        authError = nil
      }
    case .failure(let error):
      authError = error.localizedDescription
    }
  }

  private func google() async {
    guard let clientID = appState.googleConfig?.client_id,
          let presenter = googleAuth.presenter() else { return }
    busy = true
    defer { busy = false }
    do {
      let token = try await googleAuth.signIn(serverClientID: clientID, presenting: presenter)
      if let error = await appState.loginGoogle(idToken: token) {
        authError = error
      } else {
        authError = nil
      }
    } catch {
      authError = error.localizedDescription
    }
  }
}

/// 用户名/密码登录（注册也走这里，后端同一个接口）
struct PasswordSheet: View {
  @Environment(AppState.self) private var appState
  @Environment(\.dismiss) private var dismiss
  @State private var username = ""
  @State private var password = ""
  @State private var confirm = ""
  @State private var isRegister = false
  @State private var busy = false
  @State private var error: String?
  var onDone: (String?) -> Void

  var body: some View {
    NavigationStack {
      Form {
        TextField("用户名", text: $username)
          .textInputAutocapitalization(.never)
          .autocorrectionDisabled()
        SecureField("密码", text: $password)
        if isRegister {
          SecureField("再输一次", text: $confirm)
        }
        Picker("", selection: $isRegister) {
          Text("登录").tag(false)
          Text("注册").tag(true)
        }
        .pickerStyle(.segmented)
        if let error {
          Text(error).font(.caption).foregroundStyle(.red)
        }
      }
      .navigationTitle(isRegister ? "注册" : "登录")
      .navigationBarTitleDisplayMode(.inline)
      .toolbar {
        ToolbarItem(placement: .confirmationAction) {
          Button(isRegister ? "注册" : "登录") { submit() }
            .disabled(busy || username.isEmpty || password.isEmpty ||
                      (isRegister && password != confirm))
        }
        ToolbarItem(placement: .cancellationAction) {
          Button("取消") { dismiss() }
        }
      }
    }
  }

  private func submit() {
    busy = true
    Task {
      let err = isRegister
        ? await appState.registerPassword(username: username, password: password)
        : await appState.loginPassword(username: username, password: password)
      busy = false
      onDone(err)
    }
  }
}
