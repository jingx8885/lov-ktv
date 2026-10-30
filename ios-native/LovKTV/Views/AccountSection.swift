import AuthenticationServices
import SwiftUI

/// 设置页"账号"区：只显示一行状态（游客/头像+名字），
/// 点开弹窗再选登录方式或退出，主页面不再摊一堆按钮。
struct AccountSection: View {
  @Environment(AppState.self) private var appState
  @State private var showSheet = false

  var body: some View {
    Section("账号") {
      Button { showSheet = true } label: {
        HStack(spacing: 12) {
          if let user = appState.user {
            avatar(user, size: 40)
            VStack(alignment: .leading, spacing: 2) {
              Text(user.displayName)
                .font(.body.weight(.medium))
                .foregroundStyle(.primary)
              Text([user.email, user.providerTag]
                    .compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "))
                .font(.caption)
                .foregroundStyle(.secondary)
            }
          } else {
            Image(systemName: "person.crop.circle")
              .font(.title2)
              .foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 2) {
              Text("游客")
                .font(.body.weight(.medium))
                .foregroundStyle(.primary)
              Text("登录后配额/歌单/学习进度跨设备同步")
                .font(.caption)
                .foregroundStyle(.secondary)
            }
          }
          Spacer()
          Text(appState.user == nil ? "去登录" : "管理")
            .font(.caption.weight(.semibold))
            .foregroundStyle(KTV.accentColor)
          Image(systemName: "chevron.right")
            .font(.caption.weight(.bold))
            .foregroundStyle(.tertiary)
        }
        .padding(.vertical, 4)
      }
      .buttonStyle(.plain)
      .listRowBackground(KTV.card)
    }
    .sheet(isPresented: $showSheet) {
      AccountSheet()
    }
  }

  private func avatar(_ user: UserProfile, size: CGFloat) -> some View {
    ZStack {
      Circle().fill(KTV.accentColor.opacity(0.2))
      Text(String(user.displayName.prefix(1)))
        .font(.system(size: size * 0.42, weight: .bold))
        .foregroundStyle(KTV.accentColor)
    }
    .frame(width: size, height: size)
  }
}

// MARK: - 账号弹窗

private struct AccountSheet: View {
  @Environment(AppState.self) private var appState
  @Environment(\.dismiss) private var dismiss
  @State private var showPasswordSheet = false
  @State private var busy = false
  @State private var authError: String?
  private let appleAuth = AppleAuth()
  private let googleAuth = GoogleAuth()

  var body: some View {
    NavigationStack {
      Form {
        if let user = appState.user {
          profileSection(user)
        } else {
          loginSection
        }
        if let authError {
          Section {
            Text(authError).font(.caption).foregroundStyle(.red)
              .listRowBackground(KTV.card)
          }
        }
      }
      .scrollContentBackground(.hidden)
      .background(KTV.bg)
      .environment(\.colorScheme, .dark)
      .navigationTitle("账号")
      .navigationBarTitleDisplayMode(.inline)
      .toolbar {
        ToolbarItem(placement: .topBarLeading) {
          Button("关闭") { dismiss() }
        }
      }
      .presentationDetents([.medium, .large])
      .presentationDragIndicator(.visible)
      .sheet(isPresented: $showPasswordSheet) {
        PasswordSheet { error in
          authError = error
          if error == nil { showPasswordSheet = false; dismiss() }
        }
      }
    }
  }

  // MARK: 已登录

  private func profileSection(_ user: UserProfile) -> some View {
    Group {
      Section {
        HStack(spacing: 12) {
          ZStack {
            Circle().fill(KTV.accentColor.opacity(0.2))
            Text(String(user.displayName.prefix(1)))
              .font(.title3.weight(.bold))
              .foregroundStyle(KTV.accentColor)
          }
          .frame(width: 48, height: 48)
          VStack(alignment: .leading, spacing: 2) {
            Text(user.displayName)
              .font(.body.weight(.semibold))
            Text([user.email, user.providerTag]
                  .compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "))
              .font(.caption)
              .foregroundStyle(.secondary)
          }
        }
        .padding(.vertical, 4)
        .listRowBackground(KTV.card)
      }
      Section {
        Button("退出登录", role: .destructive) {
          Task {
            await appState.logout()
            dismiss()
          }
        }
        .listRowBackground(KTV.card)
      }
    }
  }

  // MARK: 游客登录

  private var loginSection: some View {
    Group {
      Section {
        Text("登录后配额、歌单、学习进度会在设备间同步。")
          .font(.caption)
          .foregroundStyle(.secondary)
          .listRowBackground(Color.clear)
      }
      Section("登录方式") {
        SignInWithAppleButton(.signIn) { request in
          request.requestedScopes = [.fullName, .email]
        } onCompletion: { result in
          Task { await apple(result) }
        }
        .signInWithAppleButtonStyle(.white)
        .frame(height: 44)
        .disabled(busy)
        .listRowBackground(KTV.card)

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
          .tint(KTV.accentColor)
          .disabled(busy)
          .listRowBackground(KTV.card)
        }

        Button {
          showPasswordSheet = true
        } label: {
          Label("用户名密码登录", systemImage: "person.badge.key")
            .foregroundStyle(KTV.accentColor)
        }
        .listRowBackground(KTV.card)

        if busy {
          HStack {
            Spacer()
            ProgressView()
            Spacer()
          }
          .listRowBackground(KTV.card)
        }
      }
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
        dismiss()
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
        dismiss()
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
          .listRowBackground(KTV.card)
        SecureField("密码", text: $password)
          .listRowBackground(KTV.card)
        if isRegister {
          SecureField("再输一次", text: $confirm)
            .listRowBackground(KTV.card)
        }
        Picker("", selection: $isRegister) {
          Text("登录").tag(false)
          Text("注册").tag(true)
        }
        .pickerStyle(.segmented)
        .listRowBackground(KTV.card)
        if let error {
          Text(error).font(.caption).foregroundStyle(.red)
            .listRowBackground(KTV.card)
        }
      }
      .scrollContentBackground(.hidden)
      .background(KTV.bg)
      .environment(\.colorScheme, .dark)
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
      .presentationDetents([.medium])
      .presentationDragIndicator(.visible)
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
