import SwiftUI

/// 设置页：连接状态卡（点开弹出连接配置）+ 账号 + 本机数据管理。
/// 连接表单收敛进 sheet，主页面不再展开一堆字段。
struct SettingsView: View {
  @Environment(AppState.self) private var appState
  var onConnected: () -> Void

  @State private var mode: ConnectionMode = .selfHosted
  @State private var server = ""
  @State private var room = ""
  @State private var apiKey = ""
  @State private var fieldError: String?
  @State private var connecting = false
  @State private var showScanner = false
  @State private var confirmForget = false
  @State private var showConnectSheet = false

  var body: some View {
    NavigationStack {
      ZStack {
        KTVBackground()
        Form {
          connectionCard
          AccountSection()
          deviceSection
          aboutSection
        }
        .scrollContentBackground(.hidden)
        .environment(\.colorScheme, .dark)
      }
      .navigationTitle("设置")
      .navigationBarTitleDisplayMode(.inline)
      .onLongPressGesture(minimumDuration: 1.5) {
        Task { await debugOfficialConnect() }
      }
      .sheet(isPresented: $showConnectSheet, onDismiss: {
        if appState.connection != nil, fieldError == nil { onConnected() }
      }) {
        ConnectionSheet(
          mode: $mode, server: $server, room: $room, apiKey: $apiKey,
          fieldError: $fieldError, connecting: $connecting,
          showScanner: $showScanner, confirmForget: $confirmForget,
          appState: appState,
          prefill: prefill, connect: connect)
      }
      .sheet(isPresented: $showScanner) {
        if QRScannerSheet.isAvailable {
          QRScannerSheet { value in
            showScanner = false
            if let parsed = try? ConnectionValidator.parse(value, room: room) {
              server = parsed.server.absoluteString
              room = parsed.room
              appState.showStatus("二维码已填入，请核对后点连接")
            } else {
              appState.showStatus("二维码内容不是有效的服务器地址")
            }
          } onDismiss: {
            showScanner = false
          }
        } else {
          Text("此设备不支持扫码，请手动填写地址").padding()
        }
      }
      .confirmationDialog("断开连接并删除本机保存的地址、房间码、屏蔽列表和 API key？",
                          isPresented: $confirmForget, titleVisibility: .visible) {
        Button("断开并清除", role: .destructive) {
          appState.disconnect()
          server = ""
          room = ""
          apiKey = ""
          fieldError = nil
          showConnectSheet = false
        }
        Button("取消", role: .cancel) {}
      }
    }
  }

  // MARK: - 连接状态卡（点开弹窗）

  private var connectionCard: some View {
    Section {
      Button {
        prefill()
        showConnectSheet = true
      } label: {
        HStack(spacing: 12) {
          Image(systemName: appState.connection == nil ? "wifi.slash" : "checkmark.circle.fill")
            .font(.title2)
            .foregroundStyle(appState.connection == nil ? Color.secondary : KTV.lime)
          VStack(alignment: .leading, spacing: 2) {
            Text(appState.connection == nil ? "未连接"
                 : appState.connection?.mode == .official ? "已连接 · 官方服务" : "已连接 · 自己的服务器")
              .font(.body.weight(.medium))
              .foregroundStyle(.primary)
            Text(appState.connection.map {
              "\($0.server.host ?? $0.server.absoluteString) · 房间 \($0.room)"
            } ?? "点这里连接自己的服务器或官方服务")
              .font(.caption)
              .foregroundStyle(.secondary)
          }
          Spacer()
          if appState.connection == nil {
            Text("去连接")
              .font(.caption.weight(.semibold))
              .foregroundStyle(KTV.accentColor)
          }
          Image(systemName: "chevron.right")
            .font(.caption.weight(.bold))
            .foregroundStyle(.tertiary)
        }
        .padding(.vertical, 4)
      }
      .buttonStyle(.plain)
      .listRowBackground(KTV.card)
      Group {
        if !appState.apiKeyValid {
          Label("API key 无效或已失效，请打开连接设置更新", systemImage: "key.fill")
            .font(.caption)
            .foregroundStyle(.orange)
        }
      }
      .listRowBackground(KTV.card)
    }
  }

  private var deviceSection: some View {
    Section("本机") {
      Button("清除屏蔽列表") {
        appState.clearBlocklist()
      }
      .listRowBackground(KTV.card)
      if appState.preview.playingID != nil || appState.preview.downloading {
        Button("停止手机试听") {
          appState.preview.stop()
        }
        .listRowBackground(KTV.card)
      }
    }
  }

  private var aboutSection: some View {
    Section("关于") {
      LabeledContent("版本", value: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "-")
        .listRowBackground(KTV.card)
      LabeledContent("构建", value: Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "-")
        .listRowBackground(KTV.card)
    }
  }

  /// 官方接入调试：直接注入 key+房间，跳过表单。
  /// 触发方式：在设置页任意处长按 1.5 秒。仅开发用。
  /// key 写在设备的 UserDefaults `LOVKTV_OFFICIAL_KEY` 里，不进 git。
  private func debugOfficialConnect() async {
    guard let key = UserDefaults.standard.string(forKey: "LOVKTV_OFFICIAL_KEY"),
          !key.isEmpty else {
      appState.showStatus("先在设备 defaults 写 LOVKTV_OFFICIAL_KEY")
      return
    }
    if let error = await appState.officialInject(apiKey: key, roomCode: "9B4D9C") {
      appState.showStatus(error)
    }
  }

  private func prefill() {
    guard let conn = appState.connection else { return }
    mode = conn.mode
    server = conn.mode == .official ? "" : conn.server.absoluteString
    room = conn.room
  }

  private func connect() {
    fieldError = nil
    connecting = true
    Task {
      let error = await appState.connect(mode: mode, serverRaw: server, roomCode: room, apiKey: apiKey)
      connecting = false
      if let error {
        fieldError = error
      } else {
        apiKey = ""
        showConnectSheet = false   // 成功就收起弹窗；onDismiss 里跳回点歌台
      }
    }
  }
}

// MARK: - 连接配置弹窗

private struct ConnectionSheet: View {
  @Binding var mode: ConnectionMode
  @Binding var server: String
  @Binding var room: String
  @Binding var apiKey: String
  @Binding var fieldError: String?
  @Binding var connecting: Bool
  @Binding var showScanner: Bool
  @Binding var confirmForget: Bool
  let appState: AppState
  let prefill: () -> Void
  let connect: () -> Void
  @Environment(\.dismiss) private var dismiss

  var body: some View {
    NavigationStack {
      Form {
        Section {
          Picker("连接方式", selection: $mode) {
            Text("自己的服务器").tag(ConnectionMode.selfHosted)
            Text("官方服务").tag(ConnectionMode.official)
          }
          .pickerStyle(.segmented)
          .listRowBackground(KTV.card)
        }

        Section("地址") {
          if mode == .selfHosted {
            HStack {
              TextField("服务器地址，例如 http://192.168.1.8:8790", text: $server)
                .keyboardType(.URL)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
              Button { showScanner = true } label: {
                Image(systemName: "qrcode.viewfinder")
              }
              .accessibilityLabel("扫码")
            }
            .listRowBackground(KTV.card)
            TextField("房间码，例如 K7Q2", text: $room)
              .textInputAutocapitalization(.characters)
              .autocorrectionDisabled()
              .listRowBackground(KTV.card)
          } else {
            Button {
              Task { _ = await appState.startOfficialConnect(roomCode: room) }
            } label: {
              Label("浏览器一键接入", systemImage: "safari")
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .tint(KTV.accentColor)
            .listRowBackground(KTV.card)
            SecureField("API key（lkr_ 开头）", text: $apiKey)
              .textInputAutocapitalization(.never)
              .autocorrectionDisabled()
              .listRowBackground(KTV.card)
            TextField("房间码，例如 K7Q2", text: $room)
              .textInputAutocapitalization(.characters)
              .autocorrectionDisabled()
              .listRowBackground(KTV.card)
            Text("官方服务地址：ktv.lovbrowser.com。API key 只保存在本机钥匙串。")
              .font(.caption)
              .foregroundStyle(.secondary)
              .listRowBackground(KTV.card)
          }
          if let fieldError {
            Text(fieldError)
              .font(.caption)
              .foregroundStyle(.red)
              .listRowBackground(KTV.card)
          }
        }

        Section {
          Button(action: connect) {
            HStack {
              Spacer()
              if connecting { ProgressView().padding(.trailing, 4) }
              Text(appState.connection == nil ? "连接" : "重新连接")
                .fontWeight(.semibold)
              Spacer()
            }
          }
          .disabled(connecting)
          .listRowBackground(KTV.card)
        }

        if appState.connection != nil {
          Section {
            Button("断开并清除本机数据", role: .destructive) {
              confirmForget = true
            }
            .listRowBackground(KTV.card)
          }
        }
      }
      .scrollContentBackground(.hidden)
      .background(KTV.bg)
      .environment(\.colorScheme, .dark)
      .navigationTitle("连接")
      .navigationBarTitleDisplayMode(.inline)
      .toolbar {
        ToolbarItem(placement: .topBarLeading) {
          Button("取消") { dismiss() }
        }
      }
      .presentationDetents([.large])
      .presentationDragIndicator(.visible)
      .onAppear { prefill() }
    }
  }
}
