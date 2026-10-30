import SwiftUI

@main
struct LovKTVApp: App {
  @State private var appState = AppState()
  @State private var library = LibraryStore()

  var body: some Scene {
    WindowGroup {
      ContentView()
        .environment(appState)
        .environment(library)
        .task {
          // 恢复上次的连接
          if appState.connection != nil {
            library.client = appState.client
            _ = await appState.refresh()
          }
        }
        .onOpenURL { url in
          // lovktv://official?key=...&room=... —— 官方一键接入回跳
          Task {
            if let error = await appState.handleDeepLink(url) {
              appState.showStatus(error)
            }
          }
        }
    }
  }
}
