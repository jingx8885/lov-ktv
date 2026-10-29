import SwiftUI

/// 单词本（多邻国式）：词库总览 → 一轮抽认卡/选择/拼词题 → 结算，带连续天数。
struct ReciteView: View {
  @Environment(AppState.self) private var appState
  @State private var deck: ReciteDeck?
  @State private var error: String?
  @State private var loading = true

  var body: some View {
    NavigationStack {
      if appState.connection == nil {
        ContentUnavailableView("未连接", systemImage: "book.closed",
                               description: Text("先在设置里连接服务器。"))
          .navigationTitle("单词本")
      } else if appState.connection?.mode == .official {
        ContentUnavailableView("暂不可用", systemImage: "book.closed",
                               description: Text("官方服务暂未开放单词本接口。"))
          .navigationTitle("单词本")
      } else if loading {
        ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
      } else if let error {
        ContentUnavailableView("打不开", systemImage: "exclamationmark.triangle",
                               description: Text(error))
          .navigationTitle("单词本")
      } else {
        body_(deck ?? ReciteDeck(deck: "word", total: 0, due: 0, new: 0, learning: 0,
                                 mastered: 0, skipped: 0, streak: 0, today: 0, sizes: [10,20,30], cards: nil))
      }
    }
    .task(id: appState.connection) { await load() }
  }

  @ViewBuilder
  private func body_(_ d: ReciteDeck) -> some View {
    List {
      Section {
        HStack(spacing: 12) {
          statBubble("总词", d.total, .blue)
          statBubble("到期", d.due, .orange)
          statBubble("新词", d.new, .purple)
          statBubble("在学", d.learning, .yellow)
          statBubble("已会", d.mastered, .green)
        }
        .padding(.vertical, 4)
      } header: {
        HStack {
          Text("词库")
          Spacer()
          if d.streak > 0 {
            Label("\(d.streak) 天", systemImage: "flame.fill")
              .font(.caption.weight(.semibold))
              .foregroundStyle(.orange)
          }
        }
      }

      Section("来一轮") {
        ForEach(d.sizes, id: \.self) { size in
          NavigationLink {
            ReciteSessionView(size: size, songID: "")
          } label: {
            HStack {
              Text("\(size) 张卡")
              Spacer()
              Text(d.due >= size ? "够练" : "边凑边练")
                .font(.caption).foregroundStyle(.secondary)
            }
          }
          .disabled(d.due == 0 && d.new == 0)
        }
        if d.due == 0 && d.new == 0 {
          Text("先把歌词里的词点进单词本").font(.caption).foregroundStyle(.secondary)
        }
      }

      Section("管理") {
        NavigationLink {
          WordsManageView(state: "active")
        } label: {
          LabeledContent("在学词", value: "\(d.learning)")
        }
        NavigationLink {
          WordsManageView(state: "mastered")
        } label: {
          LabeledContent("已掌握", value: "\(d.mastered)")
        }
        NavigationLink {
          WordsManageView(state: "skipped")
        } label: {
          LabeledContent("暂存", value: "\(d.skipped)")
        }
      }
    }
    .listStyle(.insetGrouped)
    .navigationTitle("单词本")
    .refreshable { await load() }
  }

  private func statBubble(_ label: String, _ value: Int, _ color: Color) -> some View {
    VStack(spacing: 4) {
      Text("\(value)")
        .font(.title3.weight(.bold).monospacedDigit())
        .foregroundStyle(color)
      Text(label).font(.caption2).foregroundStyle(.secondary)
    }
    .frame(maxWidth: .infinity)
  }

  private func load() async {
    guard let client = appState.client else { return }
    do {
      deck = try await client.reciteDeck()
      error = nil
    } catch {
      self.error = error.localizedDescription
    }
    loading = false
  }
}

/// 一轮抽认卡：kind 自动渲染 meaning/reverse/blank/listen/match。
/// 错的重排到队尾（网页"首次判定才算分"的规则：错一次就当miss，但仍要练到对）。
struct ReciteSessionView: View {
  @Environment(AppState.self) private var appState
  let size: Int
  let songID: String

  @State private var items: [ReciteItem] = []
  @State private var index = 0
  @State private var firstMisses: Set<String> = []
  @State private var retryQueue: [ReciteItem] = []
  @State private var picked: Int?
  @State private var matchAnswers: [String: [Int]] = [:]
  @State private var matchMisses: [String: Int] = [:]
  @State private var pickedLeft: [String: Int] = [:]
  @State private var finished = false
  @State private var submitted = false
  @State private var loading = true
  @State private var error: String?

  private var item: ReciteItem? { items[safe: index] }
  private var firstTryRight: Int { items.filter { !firstMisses.contains($0.id) }.count }

  var body: some View {
    Group {
      if loading {
        ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
      } else if let error {
        ContentUnavailableView("这轮没词", systemImage: "checkmark.circle",
                               description: Text(error))
      } else if finished {
        resultView
      } else if let item {
        cardView(item)
      }
    }
    .navigationTitle("抽认卡 \(index + 1)/\(items.count)")
    .navigationBarTitleDisplayMode(.inline)
    .task { await load() }
  }

  @ViewBuilder
  private func cardView(_ item: ReciteItem) -> some View {
    List {
      Section {
        VStack(alignment: .leading, spacing: 12) {
          Text(promptFor(item))
            .font(.title3.weight(.semibold))
          if let romaji = item.detail?.romaji, !romaji.isEmpty {
            Text(romaji).font(.subheadline).foregroundStyle(.secondary)
          }
          if let line = item.detail?.line_text, !line.isEmpty {
            Text(line).font(.caption).foregroundStyle(.secondary)
          }
        }
        .padding(.vertical, 8)
      }

      Section("选答案") {
        if item.kind == "match" {
          matchView(item)
        } else {
          ForEach(item.choices ?? []) { choice in
            Button { pick(choice.id, in: item) } label: {
              HStack {
                Text(choice.text).foregroundStyle(.primary)
                Spacer()
                if picked == choice.id {
                  Image(systemName: isRight(choice.id, in: item) ? "checkmark.circle.fill" : "xmark.circle.fill")
                    .foregroundStyle(isRight(choice.id, in: item) ? .green : .red)
                }
              }
            }
            .buttonStyle(.bordered)
            .tint(picked == choice.id ? (isRight(choice.id, in: item) ? .green : .red) : .secondary)
          }
        }
      }

      if picked != nil || item.kind == "match" {
        Section {
          if picked != nil {
            Text(isRight(picked!, in: item) ? "对了" : "错了，答案是 \(item.answer_text ?? "")")
              .font(.subheadline.weight(.medium))
              .foregroundStyle(isRight(picked!, in: item) ? .green : .orange)
            Button { next() } label: { Text(picked.map { isRight($0, in: item) } == true ? "继续" : "重练这题") }
              .buttonStyle(.borderedProminent)
          } else {
            Button("确认配对") { confirmMatch(item) }
              .buttonStyle(.borderedProminent)
              .disabled(matchAnswers[item.id]?.count != (item.pairs?.count ?? 0))
          }
        }
      }
    }
    .listStyle(.insetGrouped)
  }

  private func promptFor(_ item: ReciteItem) -> String {
    switch item.kind {
    case "meaning": return item.stem ?? ""
    case "reverse": return item.stem ?? ""
    case "blank": return item.stem ?? ""
    case "listen": return "🔊 听音选词"
    case "match": return "左右配对"
    default: return item.stem ?? item.prompt ?? ""
    }
  }

  @ViewBuilder
  private func matchView(_ item: ReciteItem) -> some View {
    let pairs = item.pairs ?? []
    let done = Set(matchAnswers[item.id] ?? [])
    ForEach(pairs) { pair in
      HStack {
        Button(pair.left) {
          pickedLeft[item.id] = pair.id
        }
        .buttonStyle(.bordered)
        .tint(done.contains(pair.id) ? .green : pickedLeft[item.id] == pair.id ? .accentColor : .secondary)
        .disabled(done.contains(pair.id))
        Image(systemName: "arrow.right").foregroundStyle(.tertiary)
        ForEach(pairs) { other in
          Button(other.right) {
            guard let left = pickedLeft[item.id] else { return }
            if left == other.id {
              matchAnswers[item.id, default: []].append(other.id)
            } else {
              matchMisses[item.id, default: 0] += 1
            }
            pickedLeft[item.id] = nil
          }
          .buttonStyle(.bordered)
          .tint(done.contains(other.id) ? .green : .secondary)
          .disabled(done.contains(other.id))
        }
      }
    }
  }

  private var resultView: some View {
    List {
      Section("这轮") {
        HStack {
          stat("答对", firstTryRight, .green)
          stat("答错", firstMisses.count, .orange)
          stat("正确率", items.isEmpty ? 0 : Int(round(Double(firstTryRight) / Double(items.count) * 100)), .blue)
        }
      }
      Section {
        Button(submitted ? "已完成" : "完成") { submit() }
          .buttonStyle(.borderedProminent)
          .disabled(submitted)
      }
    }
    .listStyle(.insetGrouped)
  }

  private func stat(_ label: String, _ value: Int, _ color: Color) -> some View {
    VStack(spacing: 4) {
      Text("\(value)").font(.title2.weight(.bold)).foregroundStyle(color)
      Text(label).font(.caption).foregroundStyle(.secondary)
    }
    .frame(maxWidth: .infinity)
  }

  private func isRight(_ choice: Int, in item: ReciteItem) -> Bool {
    choice == item.answer
  }

  private func pick(_ choice: Int, in item: ReciteItem) {
    guard picked == nil else { return }
    picked = choice
    if !isRight(choice, in: item) {
      firstMisses.insert(item.id)
    }
  }

  private func confirmMatch(_ item: ReciteItem) {
    let total = item.pairs?.count ?? 0
    let right = matchAnswers[item.id]?.count ?? 0
    if right < total { firstMisses.insert(item.id) }
    picked = -1 // 标记已判
    next()
  }

  private func next() {
    if picked != nil, let item, !isRight(picked!, in: item) {
      // 错的塞队尾再练
      if !retryQueue.contains(where: { $0.id == item.id }) {
        retryQueue.append(item)
      }
    }
    picked = nil
    pickedLeft = [:]
    if index + 1 < items.count {
      index += 1
    } else if !retryQueue.isEmpty {
      items.append(contentsOf: retryQueue)
      retryQueue = []
      index += 1
    } else {
      finished = true
    }
  }

  private func load() async {
    guard let client = appState.client else { return }
    do {
      let s = try await client.reciteSession(size: size, songID: songID)
      items = s.cards
      if items.isEmpty { error = "今天没有到期的卡" }
    } catch {
      self.error = error.localizedDescription
    }
    loading = false
  }

  private func submit() {
    guard let client = appState.client else { return }
    let packed: [[String: AnyEncodable]] = items.map { item in
      ["card_id": AnyEncodable(item.card_id ?? item.id),
       "ok": AnyEncodable(!firstMisses.contains(item.id))]
    }
    Task {
      do {
        _ = try await client.submitRecite(songID: songID, answers: packed)
        submitted = true
      } catch {
        appState.showStatus(error.localizedDescription)
      }
    }
  }
}

/// 单词管理：按状态列词，可恢复/移除
struct WordsManageView: View {
  @Environment(AppState.self) private var appState
  let state: String
  @State private var words: [ReciteCard] = []
  @State private var loading = true

  var body: some View {
    List {
      ForEach(words) { w in
        VStack(alignment: .leading, spacing: 4) {
          Text(w.text ?? "")
          Text([w.zh, w.romaji, w.song_title].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "))
            .font(.caption).foregroundStyle(.secondary)
        }
        .swipeActions(edge: .trailing) {
          if w.skipped == true {
            Button("恢复") { restore(w) }.tint(.green)
          } else {
            Button("暂存") { drop(w) }.tint(.orange)
          }
        }
      }
      if words.isEmpty && !loading {
        Text("这里还没有词").foregroundStyle(.secondary)
      }
    }
    .navigationTitle(state == "mastered" ? "已掌握" : state == "skipped" ? "暂存" : "在学")
    .task { await load() }
  }

  private func load() async {
    guard let client = appState.client else { return }
    words = (try? await client.wordsList(state: state)) ?? []
    loading = false
  }

  private func restore(_ w: ReciteCard) {
    guard let client = appState.client else { return }
    Task {
      _ = try? await client.restoreWord(w.card_id)
      await load()
    }
  }

  private func drop(_ w: ReciteCard) {
    guard let client = appState.client else { return }
    Task {
      try? await client.dropWord(w.card_id)
      await load()
    }
  }
}
