import SwiftUI

/// 点唱（read 技能 play_mode=tap）：歌词跟歌滚动，按顺序点每个词。
/// 对齐网页 tap：combo/perfect/hits/misses；% = hits/totalWords。
struct TapGameView: View {
  @Environment(AppState.self) private var appState
  let song: Song
  let lines: [Lesson.LessonLine]

  @State private var currentLine = 0
  @State private var cursor = 0
  @State private var hits = 0
  @State private var misses = 0
  @State private var combo = 0
  @State private var maxCombo = 0
  @State private var perfect = 0
  @State private var done = false
  @State private var finished = false
  @State private var score: Int?
  @State private var playingLine = false
  @State private var flashWord = ""
  @State private var clock: Task<Void, Never>?

  private let graceMS = 6000
  private var totalWords: Int { lines.reduce(0) { $0 + ($1.words?.count ?? 0) } }
  private var pct: Int { totalWords > 0 ? Int(round(Double(hits) / Double(totalWords) * 100)) : 0 }
  private var line: Lesson.LessonLine? { lines[safe: currentLine] }
  private var lineComplete: Bool { cursor >= (line?.words?.count ?? 0) }

  var body: some View {
    ZStack {
      Color.black.ignoresSafeArea()
      if finished {
        resultView
      } else {
        gameView
      }
    }
    .navigationBarTitleDisplayMode(.inline)
    .onAppear { start() }
    .onDisappear { stopAll() }
  }

  // MARK: - 舞台

  private var gameView: some View {
    VStack(spacing: 0) {
      // 顶部：进度 + 播放控制 + combo
      header
      // 中央当前行
      Spacer()
      lineCard
      Spacer()
      // 底部：已点词条 + 下一行按钮 + 磁贴盘
      bottom
    }
  }

  private var header: some View {
    VStack(spacing: 8) {
      HStack {
        Text("点唱 · \(song.displayTitle)")
          .font(.subheadline.weight(.medium))
        Spacer()
        Text("COMBO \(combo)")
          .font(.system(.callout, design: .monospaced).weight(.bold))
          .foregroundStyle(combo > 0 ? .orange : .secondary)
          .contentTransition(.numericText())
      }
      ProgressView(value: totalWords > 0 ? Double(hits + misses) / Double(totalWords) : 0)
        .tint(.accentColor)
      HStack {
        Text("\(currentLine + 1) / \(lines.count) 句")
          .font(.caption).foregroundStyle(.secondary)
        Spacer()
        Text("\(hits)✓ \(misses)✗")
          .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
      }
    }
    .padding(.horizontal, 20).padding(.top, 8)
  }

  private var lineCard: some View {
    VStack(spacing: 10) {
      if let line {
        Text(line.text ?? "")
          .font(.title.weight(.bold))
          .multilineTextAlignment(.center)
          .foregroundStyle(.white)
          .shadow(color: .accentColor.opacity(0.5), radius: 12)
        if let romaji = line.romaji, !romaji.isEmpty {
          Text(romaji).font(.subheadline).foregroundStyle(.secondary)
        }
        if let zh = line.zh, !zh.isEmpty {
          Text(zh).font(.callout).foregroundStyle(.secondary)
        }
      }
    }
    .padding(.horizontal, 24)
  }

  private var bottom: some View {
    VStack(spacing: 12) {
      // 已点到的词串
      tappedStrip
      // 未点词磁贴
      tileField
      // 控制
      HStack(spacing: 16) {
        Button { replayLine() } label: {
          Label("重听这句", systemImage: "arrow.clockwise")
        }
        .buttonStyle(.bordered)
        Button { skipLine() } label: {
          Label(lineComplete ? "下一句" : "跳过", systemImage: "forward.fill")
        }
        .buttonStyle(.borderedProminent)
      }
      .padding(.bottom, 12)
    }
  }

  private var tappedStrip: some View {
    ScrollView(.horizontal, showsIndicators: false) {
      HStack(spacing: 6) {
        ForEach(0..<cursor, id: \.self) { i in
          if let w = line?.words?[safe: i] {
            Text(w.text ?? "")
              .font(.caption.weight(.semibold))
              .padding(.horizontal, 10).padding(.vertical, 6)
              .background(Color.accentColor.opacity(0.25), in: Capsule())
              .foregroundStyle(.white)
          }
        }
      }
      .padding(.horizontal, 20)
    }
    .frame(height: 34)
  }

  private var tileField: some View {
    // 未点词的磁贴，乱序摆；点对的词消失
    let words = line?.words ?? []
    return GeometryReader { geo in
      let slots = layout(words, in: geo.size)
      ForEach(Array(words.enumerated()), id: \.offset) { i, word in
        if i >= cursor {
          tile(word, at: slots[i])
        }
      }
    }
    .frame(height: 220)
    .padding(.horizontal, 16)
  }

  private func tile(_ word: Lesson.LessonWord, at slot: (x: CGFloat, y: CGFloat, w: CGFloat, h: CGFloat)) -> some View {
    let isCurrent = line?.words?[safe: cursor]?.text == word.text && line?.words?[safe: cursor] != nil
    return Button { tap(word) } label: {
      VStack(spacing: 2) {
        Text(word.text ?? "")
          .font(.body.weight(.bold))
        if let sub = word.translation ?? word.zh, !sub.isEmpty {
          Text(sub).font(.caption2).opacity(0.85)
        }
      }
      .frame(width: slot.w, height: slot.h)
      .background(isCurrent ? Color.orange.opacity(0.9) : Color.accentColor.opacity(0.5),
                  in: RoundedRectangle(cornerRadius: 12))
      .foregroundStyle(.white)
      .shadow(radius: isCurrent ? 8 : 2)
      .scaleEffect(isCurrent ? 1.06 : 1)
      .animation(.spring(response: 0.2), value: isCurrent)
    }
    .position(x: slot.x + slot.w / 2, y: slot.y + slot.h / 2)
    .buttonStyle(.plain)
    .transition(.scale.combined(with: .opacity))
  }

  private func layout(_ words: [Lesson.LessonWord], in size: CGSize)
    -> [(x: CGFloat, y: CGFloat, w: CGFloat, h: CGFloat)] {
    // 简化乱序网格：按顺序排两行，但为了有"找"的感觉做确定性洗牌
    let order = words.indices.shuffled()
    var slots = Array(repeating: (x: CGFloat(0), y: CGFloat(0), w: CGFloat(0), h: CGFloat(0)), count: words.count)
    let cols = max(1, Int(size.width / 110))
    let cellW = size.width / CGFloat(cols)
    let cellH: CGFloat = 62
    for (pos, idx) in order.enumerated() {
      let row = pos / cols
      let col = pos % cols
      slots[idx] = (x: CGFloat(col) * cellW + 4, y: CGFloat(row) * (cellH + 8),
                    w: cellW - 8, h: cellH)
    }
    return slots
  }

  private var resultView: some View {
    VStack(spacing: 24) {
      Text(grade(score ?? pct))
        .font(.system(size: 80, weight: .black, design: .rounded))
        .foregroundStyle(gradeColor(score ?? pct))
      Text("得分 \(score ?? pct)")
        .font(.title2.weight(.semibold))
      HStack(spacing: 20) {
        stat("命中", hits)
        stat("漏了", misses)
        stat("完美句", perfect)
        stat("最长连击", maxCombo)
      }
      HStack(spacing: 16) {
        Button("再来一遍") { restart() }
          .buttonStyle(.bordered)
        Button("提交成绩") { submit() }
          .buttonStyle(.borderedProminent)
          .disabled(score != nil)
      }
      if score != nil {
        Text("已提交，回学习页看进度").font(.caption).foregroundStyle(.secondary)
      }
    }
  }

  private func stat(_ label: String, _ value: Int) -> some View {
    VStack(spacing: 4) {
      Text("\(value)").font(.title3.weight(.bold))
      Text(label).font(.caption).foregroundStyle(.secondary)
    }
  }

  private func grade(_ p: Int) -> String {
    p >= 90 ? "S" : p >= 75 ? "A" : p >= 55 ? "B" : "C"
  }
  private func gradeColor(_ p: Int) -> Color {
    p >= 90 ? .yellow : p >= 75 ? .green : p >= 55 ? .blue : .gray
  }

  // MARK: - 控制流

  private func start() {
    Task {
      guard let client = appState.client else { return }
      _ = await appState.player.open(song: song, client: client)
      appState.player.resume()
      drive()
    }
  }

  private func drive() {
    clock?.cancel()
    clock = Task { [self] in
      while !Task.isCancelled, !finished {
        await tick()
        try? await Task.sleep(for: .milliseconds(100))
      }
    }
  }

  private func tick() async {
    let ms = appState.player.currentMS
    // 时间推进：过期的行补记 miss
    for (i, line) in lines.enumerated() {
      if i == currentLine { continue }
      if (line.end_ms ?? 0) + graceMS < ms && !isDone(i) {
        finishLine(i, hit: 0, total: line.words?.count ?? 0)
      }
    }
    // 当前行推进：时间到下一句且本句已完
    if let line, let next = lines[safe: currentLine + 1],
       ms >= next.start_ms ?? 0 {
      if lineComplete {
        advance()
      } else {
        finishLine(currentLine, hit: cursor, total: line.words?.count ?? 0)
        advance()
      }
    }
    // 播完整首歌且还有未完的
    if ms >= (lines.last?.end_ms ?? 0) + graceMS && currentLine < lines.count {
      finishLine(currentLine, hit: cursor, total: line?.words?.count ?? 0)
      finish()
    }
  }

  private func isDone(_ i: Int) -> Bool { i < currentLine }

  private func tap(_ word: Lesson.LessonWord) {
    guard let line, !lineComplete else { return }
    let expected = line.words?[safe: cursor]
    if expected?.text == word.text {
      cursor += 1
      hits += 1
      combo += 1
      maxCombo = max(maxCombo, combo)
      UIImpactFeedbackGenerator(style: .medium).impactOccurred()
      flashWord = word.text ?? ""
      if lineComplete { perfect += 1 }
    } else {
      combo = 0
      misses += 1
      UIImpactFeedbackGenerator(style: .heavy).impactOccurred()
    }
  }

  private func advance() {
    currentLine += 1
    cursor = 0
    if currentLine >= lines.count {
      finish()
    }
  }

  private func finishLine(_ index: Int, hit: Int, total: Int) {
    let left = total - hit
    if left > 0 { misses += left }
  }

  private func finish() {
    finished = true
    clock?.cancel()
    appState.player.pause()
  }

  private func replayLine() {
    guard let line else { return }
    appState.player.seekMS(line.start_ms ?? 0)
    appState.player.resume()
  }

  private func skipLine() {
    if lineComplete { perfect += 1 }
    advance()
  }

  private func restart() {
    currentLine = 0
    cursor = 0
    hits = 0; misses = 0; combo = 0; maxCombo = 0; perfect = 0
    finished = false; score = nil
    appState.player.resume()
    drive()
  }

  private func stopAll() {
    clock?.cancel()
    appState.player.pause()
  }

  private func submit() {
    guard let client = appState.client else { return }
    Task {
      do {
        let r = try await client.submitLesson(
          song.songID, unit: "u0", skill: "read",
          attemptID: UUID().uuidString, pct: pct, answers: nil)
        score = r.pct ?? pct
        appState.showStatus("成绩已提交")
      } catch {
        score = pct
        appState.showStatus(error.localizedDescription)
      }
    }
  }
}
