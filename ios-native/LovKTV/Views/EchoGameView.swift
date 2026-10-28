import AVFoundation
import SwiftUI

/// 跟唱：逐句听原唱→自己唱→按音量覆盖率打分，可回放自己的录音。
/// 提交到 read 技能（同点唱）。
struct EchoGameView: View {
  @Environment(AppState.self) private var appState
  let song: Song
  let lines: [Lesson.LessonLine]

  @State private var index = 0
  @State private var phase: Phase = .listen
  @State private var scores: [Int?] = []
  @State private var recordings: [URL?] = []
  @State private var finished = false
  @State private var submitted = false
  @State private var recording = false
  @State private var recorder = SingRecorder()
  @State private var playPlayer: AVAudioPlayer?

  enum Phase { case listen, sing, review }

  private var line: Lesson.LessonLine? { lines[safe: index] }
  private var pct: Int {
    let done = scores.compactMap { $0 }
    return done.isEmpty ? 0 : done.reduce(0, +) / done.count
  }

  var body: some View {
    ZStack {
      Color.black.ignoresSafeArea()
      if finished { resultView } else { stage }
    }
    .navigationBarTitleDisplayMode(.inline)
    .onAppear { prepare() }
    .onDisappear { stopAll() }
  }

  private var stage: some View {
    VStack(spacing: 20) {
      header
      Spacer()
      lineCard
      micMeter
      Spacer()
      controls
    }
    .padding(20)
  }

  private var header: some View {
    VStack(spacing: 8) {
      Text("跟唱 · \(song.displayTitle)")
        .font(.subheadline.weight(.medium))
      HStack {
        Text("第 \(index + 1) / \(lines.count) 句")
          .font(.caption).foregroundStyle(.secondary)
        Spacer()
        Text(phase == .listen ? "听一遍" : phase == .sing ? "唱这句" : "回放")
          .font(.caption.weight(.semibold))
          .foregroundStyle(phase == .sing ? .red : .accentColor)
      }
      ProgressView(value: Double(index) / Double(max(1, lines.count)))
        .tint(.accentColor)
    }
  }

  private var lineCard: some View {
    VStack(spacing: 10) {
      if let line {
        Text(line.text ?? "")
          .font(.title.weight(.bold))
          .multilineTextAlignment(.center)
        if let r = line.romaji, !r.isEmpty {
          Text(r).font(.subheadline).foregroundStyle(.secondary)
        }
        if let z = line.zh, !z.isEmpty {
          Text(z).font(.callout).foregroundStyle(.secondary)
        }
      }
    }
  }

  private var micMeter: some View {
    // 录音电平条
    let db = max(0, (Double(recorder.level) + 60) / 60)
    return HStack(spacing: 6) {
      Image(systemName: recording ? "mic.fill" : "mic")
        .foregroundStyle(recording ? .red : .secondary)
      GeometryReader { geo in
        RoundedRectangle(cornerRadius: 3)
          .fill(.secondary.opacity(0.2))
          .overlay(alignment: .leading) {
            RoundedRectangle(cornerRadius: 3)
              .fill(LinearGradient(colors: [.green, .yellow, .red], startPoint: .leading, endPoint: .trailing))
              .frame(width: geo.size.width * db)
          }
      }
      .frame(height: 8)
    }
    .frame(height: 20)
  }

  private var controls: some View {
    VStack(spacing: 12) {
      if phase == .listen {
        Button { sing() } label: {
          Label("我唱这句", systemImage: "mic")
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(.borderedProminent)
      } else if phase == .sing {
        Button { stopSing() } label: {
          Label("唱完了", systemImage: "stop.fill")
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(.borderedProminent)
        .tint(.red)
      } else {
        HStack(spacing: 12) {
          Button { replayRecording() } label: {
            Label("听自己", systemImage: "play.fill")
          }
          .buttonStyle(.bordered)
          Button { resing() } label: {
            Label("重唱", systemImage: "arrow.counterclockwise")
          }
          .buttonStyle(.bordered)
          Button { nextLine() } label: {
            Label("下一句", systemImage: "forward.fill")
          }
          .buttonStyle(.borderedProminent)
        }
      }
      Button { skip() } label: { Text("跳过这句") }
        .buttonStyle(.plain)
        .foregroundStyle(.secondary)
    }
  }

  private var resultView: some View {
    VStack(spacing: 24) {
      Text("\(pct)")
        .font(.system(size: 90, weight: .black, design: .rounded))
        .foregroundStyle(pct >= 70 ? .green : .orange)
      Text(pct >= 70 ? "唱得不错" : "再来一遍会更好")
        .font(.title3)
      let scored = scores.compactMap { $0 }.count
      Text("唱了 \(scored) / \(lines.count) 句")
        .foregroundStyle(.secondary)
      HStack(spacing: 16) {
        Button("再来一遍") { restart() }
          .buttonStyle(.bordered)
        Button(submitted ? "已提交" : "提交成绩") { submit() }
          .buttonStyle(.borderedProminent)
          .disabled(submitted)
      }
    }
  }

  // MARK: - 流程

  private func prepare() {
    scores = Array(repeating: nil, count: lines.count)
    recordings = Array(repeating: nil, count: lines.count)
    Task {
      guard let client = appState.client else { return }
      _ = await appState.player.open(song: song, client: client)
      listen()
    }
  }

  private func listen() {
    guard let line else { return }
    phase = .listen
    appState.player.seekMS(line.start_ms ?? 0)
    appState.player.resume()
    Task {
      // 放到这句结束再停
      try? await Task.sleep(for: .milliseconds((line.end_ms ?? 0) - (line.start_ms ?? 0) + 400))
      appState.player.pause()
    }
  }

  private func sing() {
    let url = FileManager.default.temporaryDirectory
      .appendingPathComponent("sing-\(song.songID)-\(index).wav")
    phase = .sing
    Task {
      do {
        try await recorder.start(to: url)
        recording = true
      } catch {
        appState.showStatus(error.localizedDescription)
        phase = .review
      }
    }
  }

  private func stopSing() {
    recording = false
    let url = recorder.stop()
    recordings[index] = url
    let coverage = url.map { SingRecorder.score(file: $0) } ?? 0
    let line = lines[safe: index]
    let want = Double((line?.end_ms ?? 0) - (line?.start_ms ?? 0)) / 1000
    let got = (try? url?.resourceValues(forKeys: [.fileSizeKey]).fileSize).map { Double($0) / 32000.0 } ?? 0
    let fit = want > 0 ? max(0, 1 - abs(min(got, want) - want) / want) : 0
    scores[index] = Int(round(coverage * 70 + fit * 30))
    phase = .review
  }

  private func resing() { sing() }
  private func skip() { scores[index] = scores[index] ?? 0; nextLine() }

  private func replayRecording() {
    guard let url = recordings[index] else { return }
    playPlayer = try? AVAudioPlayer(contentsOf: url)
    playPlayer?.play()
  }

  private func nextLine() {
    playPlayer?.stop()
    if index + 1 < lines.count {
      index += 1
      phase = .listen
      listen()
    } else {
      finish()
    }
  }

  private func finish() {
    finished = true
    appState.player.pause()
    _ = recorder.stop()
  }

  private func restart() {
    index = 0
    scores = Array(repeating: nil, count: lines.count)
    recordings = Array(repeating: nil, count: lines.count)
    finished = false
    submitted = false
    listen()
  }

  private func stopAll() {
    appState.player.pause()
    _ = recorder.stop()
    playPlayer?.stop()
  }

  private func submit() {
    guard let client = appState.client else { return }
    Task {
      do {
        _ = try await client.submitLesson(
          song.songID, unit: "u0", skill: "read",
          attemptID: UUID().uuidString, pct: pct, answers: nil)
        submitted = true
        appState.showStatus("成绩已提交")
      } catch {
        appState.showStatus(error.localizedDescription)
      }
    }
  }
}
