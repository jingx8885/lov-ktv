import SwiftUI

/// read 技能入口：选点唱或跟唱，载入 lesson lines 后进对应玩法。
struct PracticeEntryView: View {
  @Environment(AppState.self) private var appState
  let song: Song
  @State private var lesson: Lesson?
  @State private var error: String?
  @State private var picked: Mode?

  enum Mode: String, Identifiable {
    case tap, echo
    var id: String { rawValue }
    var title: String { self == .tap ? "点唱" : "跟唱" }
    var icon: String { self == .tap ? "hand.tap.fill" : "mic.fill" }
    var hint: String {
      self == .tap ? "歌词跟歌滚动，按顺序点每个词" : "逐句听原唱再自己唱，按音量打分"
    }
  }

  var body: some View {
    Group {
      if let lesson, let picked {
        switch picked {
        case .tap: TapGameView(song: song, lines: lesson.lines)
        case .echo: EchoGameView(song: song, lines: lesson.lines)
        }
      } else if let error {
        ContentUnavailableView("这节课打不开", systemImage: "exclamationmark.triangle",
                               description: Text(error))
      } else if let lesson {
        modePicker(lesson)
      } else {
        ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
      }
    }
    .navigationTitle("练习")
    .task { await load() }
  }

  @ViewBuilder
  private func modePicker(_ lesson: Lesson) -> some View {
    VStack(spacing: 20) {
      Text(song.displayTitle).font(.title3.weight(.semibold))
      Text("这首歌共 \(lesson.lines.count) 句").foregroundStyle(.secondary)
      ForEach([Mode.tap, .echo]) { mode in
        Button { picked = mode } label: {
          HStack(spacing: 16) {
            Image(systemName: mode.icon).font(.title2)
            VStack(alignment: .leading) {
              Text(mode.title).font(.headline)
              Text(mode.hint).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            Image(systemName: "chevron.right").foregroundStyle(.secondary)
          }
          .padding()
          .background(Color.accentColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 16))
          .foregroundStyle(.primary)
        }
        .buttonStyle(.plain)
      }
      Spacer()
    }
    .padding(24)
  }

  private func load() async {
    guard let client = appState.client else { return }
    do {
      lesson = try await client.learnLesson(song.songID, unit: "u0", skill: "read")
      if lesson?.lines.isEmpty != false { error = "这首歌没有可练的歌词" }
    } catch {
      self.error = error.localizedDescription
    }
  }
}
