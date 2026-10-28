import SwiftUI

enum AppTab: Hashable { case remote, library, listen, learn, settings }

struct ContentView: View {
  @Environment(AppState.self) private var appState
  @Environment(LibraryStore.self) private var library
  @State private var tab: AppTab = .settings
  @State private var listeningTitle: String?

  var body: some View {
    TabView(selection: $tab) {
      RemoteView(onGoSettings: { tab = .settings })
        .tabItem { Label("遥控", systemImage: "dot.radiowaves.left.and.right") }
        .tag(AppTab.remote)
        .badge(appState.visibleQueue.count)

      LibraryView(listeningTitle: $listeningTitle)
        .tabItem { Label("曲库", systemImage: "music.note.list") }
        .tag(AppTab.library)

      ListenView()
        .tabItem { Label("听歌", systemImage: "headphones") }
        .tag(AppTab.listen)

      LearnView()
        .tabItem { Label("学习", systemImage: "graduationcap") }
        .tag(AppTab.learn)

      SettingsView(onConnected: { tab = .remote })
        .tabItem { Label("设置", systemImage: "gearshape") }
        .tag(AppTab.settings)
    }
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
