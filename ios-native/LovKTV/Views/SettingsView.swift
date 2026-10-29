import SwiftUI

/// 设置页：连接（自己的服务器 / 官方服务）+ 本机数据管理。
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

  var body: some View {
    NavigationStack {
      Form {
        connectionCard
        AccountSection()
        form
        deviceSection
        aboutSection
      }
      .navigationTitle("设置")
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
        }
        Button("取消", role: .cancel) {}
      }
      .onAppear { prefill() }
    }
  }

  private var connectionCard: some View {
    Section {
      HStack(spacing: 12) {
        Image(systemName: appState.connection == nil ? "wifi.slash" : "checkmark.circle.fill")
          .font(.title2)
          .foregroundStyle(appState.connection == nil ? Color.secondary : Color.green)
        VStack(alignment: .leading, spacing: 2) {
          Text(appState.connection == nil ? "未连接"
               : appState.connection?.mode == .official ? "已连接 · 官方服务" : "已连接 · 自己的服务器")
            .font(.body.weight(.medium))
          Text(appState.connection.map {
            "\($0.server.host ?? $0.server.absoluteString) · 房间 \($0.room)"
          } ?? "连接自己的服务器或官方服务")
            .font(.caption)
            .foregroundStyle(.secondary)
        }
      }
      .padding(.vertical, 4)
      if !appState.apiKeyValid {
        Label("API key 无效或已失效，请在下方更新后重新连接", systemImage: "key.fill")
          .font(.caption)
          .foregroundStyle(.orange)
      }
    }
  }

  private var form: some View {
    Section {
      Picker("连接方式", selection: $mode) {
        Text("自己的服务器").tag(ConnectionMode.selfHosted)
        Text("官方服务").tag(ConnectionMode.official)
      }
      .pickerStyle(.segmented)

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
        TextField("房间码，例如 K7Q2", text: $room)
          .textInputAutocapitalization(.characters)
          .autocorrectionDisabled()
      } else {
        SecureField("API key（lkr_ 开头）", text: $apiKey)
          .textInputAutocapitalization(.never)
          .autocorrectionDisabled()
        TextField("房间码，例如 K7Q2", text: $room)
          .textInputAutocapitalization(.characters)
          .autocorrectionDisabled()
        Text("官方服务地址：ktv.lovbrowser.com。API key 只保存在本机钥匙串。")
          .font(.caption)
          .foregroundStyle(.secondary)
      }

      if let fieldError {
        Text(fieldError)
          .font(.caption)
          .foregroundStyle(.red)
      }

      Button {
        connect()
      } label: {
        HStack {
          if connecting { ProgressView() }
          Text(appState.connection == nil ? "连接服务器" : "重新连接")
            .frame(maxWidth: .infinity)
        }
      }
      .disabled(connecting)
    } header: {
      Text("连接")
    }
  }

  private var deviceSection: some View {
    Section("本机") {
      if appState.connection != nil {
        Button("断开并清除本机数据", role: .destructive) {
          confirmForget = true
        }
      }
      Button("清除屏蔽列表") {
        appState.clearBlocklist()
      }
      if appState.preview.playingID != nil || appState.preview.downloading {
        Button("停止手机试听") {
          appState.preview.stop()
        }
      }
    }
  }

  private var aboutSection: some View {
    Section("关于") {
      LabeledContent("版本", value: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "-")
      LabeledContent("构建", value: Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "-")
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
        onConnected()
      }
    }
  }
}
