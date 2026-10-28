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
    }
  }
}
