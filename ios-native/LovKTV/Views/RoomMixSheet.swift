import SwiftUI

/// 房间设置 sheet：人声开关、麦克风增益、歌词模式/字号、显示模式。
/// 对齐 m.html 的 mix 面板；改动直接 POST /mix，服务端回快照。
struct RoomMixSheet: View {
  @Environment(AppState.self) private var appState
  @Environment(\.dismiss) private var dismiss

  var body: some View {
    NavigationStack {
      Form {
        Section("人声") {
          // 原唱/伴奏是瞬时开关，vocal_mix 0 或 1
          Button {
            let next = (appState.room?.vocal_mix ?? 0) >= 0.5 ? 0.0 : 1.0
            Task { await appState.setMix(vocalMix: next) }
          } label: {
            HStack {
              Text((appState.room?.vocal_mix ?? 0) >= 0.5 ? "原唱 · 点按切伴奏" : "伴奏 · 点按切原唱")
                .foregroundStyle(.primary)
              Spacer()
              Image(systemName: (appState.room?.vocal_mix ?? 0) >= 0.5 ? "person.wave.2.fill" : "person.slash.fill")
            }
          }
          .listRowBackground(KTV.card)
        }

        Section("麦克风") {
          MixSliderRow(title: "麦克风增益", value: appState.room?.mic_gain ?? 80) { v in
            Task { await appState.setMix(micGain: Int(v.rounded())) }
          }
          .listRowBackground(KTV.card)
        }

        Section("歌词") {
          Picker("歌词显示", selection: lyricModeBinding) {
            Text("日语").tag("ja")
            Text("翻译").tag("zh")
            Text("罗马音").tag("roma")
            Text("全部").tag("all")
          }
          Stepper(value: lyricSizeBinding, in: 10...250, step: 10) {
            LabeledContent("歌词字号", value: "\(appState.room?.lyric_size ?? 30)")
          }
          .listRowBackground(KTV.card)
        }

        Section("显示") {
          Picker("播放模式", selection: displayModeBinding) {
            Text("MV").tag("mv")
            Text("歌词").tag("lyrics")
          }
          .pickerStyle(.segmented)
          .listRowBackground(KTV.card)
        }
      }
      .environment(\.colorScheme, .dark)
      .scrollContentBackground(.hidden)
      .background(KTV.bg)
      .navigationTitle("房间设置")
      .navigationBarTitleDisplayMode(.inline)
      .toolbar {
        ToolbarItem(placement: .topBarTrailing) {
          Button("完成") { dismiss() }
        }
      }
    }
    .presentationDetents([.medium, .large])
  }

  private var lyricModeBinding: Binding<String> {
    Binding(
      get: { appState.room?.lyric_mode ?? "all" },
      set: { mode in Task { await appState.setMix(lyricMode: mode) } })
  }
  private var lyricSizeBinding: Binding<Int> {
    Binding(
      get: { appState.room?.lyric_size ?? 30 },
      set: { size in Task { await appState.setMix(lyricSize: size) } })
  }
  private var displayModeBinding: Binding<String> {
    Binding(
      get: { appState.room?.display_mode ?? "mv" },
      set: { mode in Task { await appState.setMix(displayMode: mode) } })
  }
}

private struct MixSliderRow: View {
  let title: String
  let value: Double
  let onCommit: (Double) -> Void
  @State private var draft: Double?
  var body: some View {
    VStack(alignment: .leading, spacing: 6) {
      HStack {
        Text(title)
        Spacer()
        Text("\(Int((draft ?? value).rounded()))")
          .font(.caption.monospacedDigit())
          .foregroundStyle(.secondary)
      }
      Slider(value: Binding(get: { draft ?? value }, set: { draft = $0 }),
             in: 0...100, step: 1) { editing in
        if !editing, let draft { onCommit(draft); self.draft = nil }
      }
    }
  }
}
