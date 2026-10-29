import SwiftUI

/// 一首歌的单词筛选：勾选要学的词（keep），没勾的进 skip。
/// 首次 setup 必须走这里；之后再进直接跳过。
struct SongWordsSetupView: View {
  @Environment(AppState.self) private var appState
  let song: Song

  @State private var pack: SongWordsPack?
  @State private var error: String?
  @State private var loading = true
  @State private var keep: Set<String> = []
  @State private var saving = false
  @State private var collected: Set<String> = []

  var body: some View {
    Group {
      if loading {
        ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
      } else if let error {
        ContentUnavailableView("打不开", systemImage: "exclamationmark.triangle",
                               description: Text(error))
      } else if let pack {
        setupBody(pack)
      }
    }
    .navigationTitle("选词")
    .navigationBarTitleDisplayMode(.inline)
    .task { await load() }
  }

  @ViewBuilder
  private func setupBody(_ pack: SongWordsPack) -> some View {
    List {
      Section {
        Text(pack.first_setup
             ? "第一次学这首，挑出要背的词；没选的进暂存。"
             : "再筛一遍这首的词，改 keep/skip 会刷新单词本。")
          .font(.subheadline).foregroundStyle(.secondary)
      }
      Section("这首歌的词（\(pack.words.count)）") {
        ForEach(pack.words) { word in
          wordRow(word)
        }
      }
      Section {
        Button {
          save()
        } label: {
          HStack {
            Spacer()
            if saving { ProgressView() }
            Text("开始背（\(keep.count) 个）")
            Spacer()
          }
        }
        .disabled(saving)
      }
    }
    .listStyle(.insetGrouped)
    .scrollContentBackground(.hidden)
  }

  @ViewBuilder
  private func wordRow(_ word: SongWord) -> some View {
    HStack {
      VStack(alignment: .leading, spacing: 3) {
        Text(word.text ?? "")
        Text([word.zh, word.romaji].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "))
          .font(.caption).foregroundStyle(.secondary)
        if let line = word.line_text, !line.isEmpty {
          Text(line).font(.caption2).foregroundStyle(.tertiary)
        }
      }
      Spacer()
      Button {
        toggle(word)
      } label: {
        Image(systemName: keep.contains(word.word_id) ? "checkmark.circle.fill" : "circle")
          .font(.title3)
          .foregroundStyle(keep.contains(word.word_id) ? .green : .secondary)
      }
      .buttonStyle(.plain)
      .accessibilityLabel(keep.contains(word.word_id) ? "取消选词" : "选词")
      Button {
        collect(word)
      } label: {
        Image(systemName: collected.contains(word.word_id) ? "bookmark.fill" : "bookmark")
          .font(.body)
          .foregroundStyle(collected.contains(word.word_id) ? Color.accentColor : Color.secondary)
      }
      .buttonStyle(.plain)
      .accessibilityLabel("加入单词本")
    }
  }

  private func toggle(_ word: SongWord) {
    if keep.contains(word.word_id) { keep.remove(word.word_id) }
    else { keep.insert(word.word_id) }
  }

  private func collect(_ word: SongWord) {
    guard let client = appState.client else { return }
    collected.insert(word.word_id)
    Task {
      _ = try? await client.collectWord(word, songID: song.songID, songTitle: song.displayTitle)
    }
  }

  private func save() {
    guard let client = appState.client, let pack else { return }
    saving = true
    let keepIds = pack.words.filter { keep.contains($0.word_id) }.map(\.word_id)
    let skipIds = pack.words.filter { !keep.contains($0.word_id) }.map(\.word_id)
    Task {
      defer { saving = false }
      do {
        _ = try await client.setupSongWords(song.songID, keep: keepIds, skip: skipIds)
        appState.showStatus("已存进单词本，去单词本页开练")
      } catch {
        appState.showStatus(error.localizedDescription)
      }
    }
  }

  private func load() async {
    guard let client = appState.client else { return }
    do {
      let p = try await client.songWords(song.songID)
      pack = p
      // 首次默认全选；二次保留已选的
      if p.first_setup {
        keep = Set(p.words.filter { $0.skipped != true }.map(\.word_id))
      } else {
        keep = Set(p.words.filter { $0.skipped != true }.map(\.word_id))
      }
    } catch {
      self.error = error.localizedDescription
    }
    loading = false
  }
}
