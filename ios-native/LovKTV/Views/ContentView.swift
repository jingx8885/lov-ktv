import SwiftUI

enum AppTab: Hashable { case desk, search, listen, learn, settings }

struct ContentView: View {
  @Environment(AppState.self) private var appState
  @Environment(LibraryStore.self) private var library
  @State private var tab: AppTab = {
    // 开发调试可用 LOVKTV_TAB 指定落地页；正常从点歌台开始
    switch ProcessInfo.processInfo.environment["LOVKTV_TAB"] {
    case "desk", "remote": return .desk
    case "search", "library": return .search
    case "listen": return .listen
    case "learn": return .learn
    case "settings": return .settings
    default: return .desk
    }
  }()
  @State private var listeningTitle: String?

  var body: some View {
    TabView(selection: $tab) {

      DeskView(onGoSettings: { tab = .settings },
               onGoLearn: { tab = .learn },
               listeningTitle: $listeningTitle)
        .tabItem { Label("点歌", systemImage: "music.mic") }
        .tag(AppTab.desk)
        .badge(appState.visibleQueue.count)

      LibraryView()
        .tabItem { Label("搜歌", systemImage: "magnifyingglass") }
        .tag(AppTab.search)

      ListenView()
        .tabItem { Label("听歌", systemImage: "headphones") }
        .tag(AppTab.listen)

      LearnView()
        .tabItem { Label("学习", systemImage: "graduationcap") }
        .tag(AppTab.learn)

      SettingsView(onConnected: { tab = .desk })
        .tabItem { Label("设置", systemImage: "gearshape") }
        .tag(AppTab.settings)
    }
    .background(KTVBackground())
    .tint(KTV.accentColor)
    .overlay(alignment: .bottom) {
      // 试听条：正在播放或正在下载时显示
      if appState.preview.playingID != nil || appState.preview.downloading {
        ListeningBar(player: appState.preview, title: listeningTitle) {
          appState.preview.stop()
          listeningTitle = nil
        }
        .padding(.bottom, 49)
      }
    }
    .overlay(alignment: .top) {
      if let message = appState.statusMessage {
        ToastView(message: message)
          .padding(.top, 8)
          .animation(.spring(duration: 0.3), value: appState.statusMessage)
      }
    }
    .onChange(of: appState.preview.playingID) { _, id in
      if id == nil { listeningTitle = nil }
    }
    .onChange(of: appState.connection) { _, conn in
      library.client = appState.client
      if conn == nil { library.songs = []; library.total = 0 }
    }
  }
}
