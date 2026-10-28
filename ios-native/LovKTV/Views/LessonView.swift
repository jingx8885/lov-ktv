import SwiftUI

/// 一节课：多选（word/meaning/blank/listen/reverse/sentence）或配对（match）或跟读（read play_mode=tap）。
/// 非 play_mode 技能需逐题作答后整包提交；read 自己打分后只交 pct。
struct LessonView: View {
  @Environment(AppState.self) private var appState
  let song: Song
  let unitID: String
  let skill: String
  var review = false

  @State private var lesson: Lesson?
  @State private var error: String?
  @State private var answers: [String: Int] = [:]          // item.id -> picked choice id
  @State private var matchAnswers: [String: [Int]] = [:]   // item.id -> matched right pair ids
  @State private var matchMisses: [String: Int] = [:]
  @State private var pickedLeft: [String: Int] = [:]
  @State private var score = 85
  @State private var submitting = false
  @State private var result: LessonResult?
  @State private var done = false

  var body: some View {
    Group {
      if let lesson {
        lessonBody(lesson)
      } else if let error {
        ContentUnavailableView("这节课打不开", systemImage: "exclamationmark.triangle",
                               description: Text(error))
      } else {
        ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
      }
    }
    .navigationTitle(review ? "错题复习" : "练习")
    .navigationBarTitleDisplayMode(.inline)
    .task { await load() }
    .alert("成绩", isPresented: .constant(result != nil), presenting: result) { r in
      Button(r.passed == true ? "继续" : "再试一次", role: .cancel) { done = true }
    } message: { r in
      Text("得分 \(r.pct ?? r.score ?? 0)，及格线 \(r.pass_pct ?? 70) 分")
    }
    .onChange(of: done) { _, v in if v { dismiss() } }
  }

  @Environment(\.dismiss) private var dismiss

  // MARK: - 题目渲染

  @ViewBuilder
  private func lessonBody(_ lesson: Lesson) -> some View {
    List {
      // 歌词行提示区
      if !lesson.lines.isEmpty {
        Section("歌词") {
          ForEach(lesson.lines, id: \.index) { line in
            VStack(alignment: .leading, spacing: 2) {
              Text(line.text ?? "").font(.body)
              if let r = line.romaji, !r.isEmpty {
                Text(r).font(.caption2).foregroundStyle(.secondary)
              }
              if let zh = line.zh, !zh.isEmpty {
                Text(zh).font(.caption).foregroundStyle(.secondary)
              }
            }
          }
        }
      }

      if lesson.play_mode == "tap" {
        Section("跟读") {
          Text("看着歌词读一遍，读完给自己打个分。")
            .font(.subheadline).foregroundStyle(.secondary)
          Stepper("自评 \(score) 分", value: $score, in: 0...100, step: 5)
          Button("提交成绩") { submitRead() }
            .buttonStyle(.borderedProminent)
            .disabled(submitting)
        }
      } else {
        Section("答题（\(lesson.items.count) 题）") {
          ForEach(lesson.items) { item in
            itemView(item)
          }
        }
        Section {
          Button { submit() } label: {
            HStack {
              Spacer()
              if submitting { ProgressView() } else { Text("提交") }
              Spacer()
            }
          }
          .disabled(submitting || !allAnswered(lesson))
        }
      }
    }
    .listStyle(.insetGrouped)
  }

  @ViewBuilder
  private func itemView(_ item: Lesson.LessonItem) -> some View {
    VStack(alignment: .leading, spacing: 10) {
      if let prompt = item.prompt, !prompt.isEmpty {
        Text(prompt).font(.subheadline.weight(.medium))
      }
      if let stem = item.stem, !stem.isEmpty {
        Text(stem).font(.title3.weight(.semibold))
      }
      if let romaji = item.romaji, !romaji.isEmpty {
        Text(romaji).font(.caption).foregroundStyle(.secondary)
      }
      if item.kind == "match" {
        matchView(item)
      } else {
        ForEach(item.choices ?? []) { choice in
          Button {
            answers[item.id] = choice.id
          } label: {
            HStack {
              Text(choice.text).foregroundStyle(.primary)
              Spacer()
              if answers[item.id] == choice.id {
                Image(systemName: "checkmark.circle.fill").foregroundStyle(.tint)
              }
            }
          }
          .buttonStyle(.bordered)
          .tint(answers[item.id] == choice.id ? .accentColor : .secondary)
        }
      }
    }
    .padding(.vertical, 4)
  }

  @ViewBuilder
  private func matchView(_ item: Lesson.LessonItem) -> some View {
    let pairs = item.pairs ?? []
    let leftDone = Set(matchAnswers[item.id] ?? [])
    VStack(alignment: .leading, spacing: 8) {
      Text("配对：先点左边，再点右边")
        .font(.caption).foregroundStyle(.secondary)
      ForEach(pairs) { pair in
        HStack {
          Button(pair.left) {
            pickedLeft[item.id] = pair.id
          }
          .buttonStyle(.bordered)
          .tint(pickedLeft[item.id] == pair.id ? .accentColor :
                leftDone.contains(pair.id) ? .green : .secondary)
          Image(systemName: "arrow.right").foregroundStyle(.tertiary)
          Button(pair.right) {
            guard pickedLeft[item.id] != nil else { return }
            var list = matchAnswers[item.id] ?? []
            if list.contains(pair.id) { matchMisses[item.id, default: 0] += 1 }
            else { list.append(pair.id) }
            matchAnswers[item.id] = list
            pickedLeft[item.id] = nil
          }
          .buttonStyle(.bordered)
          .tint(leftDone.contains(pair.id) ? .green : .secondary)
        }
      }
    }
  }

  private func allAnswered(_ lesson: Lesson) -> Bool {
    lesson.items.allSatisfy { item in
      if item.kind == "match" {
        return (matchAnswers[item.id]?.count ?? 0) == (item.pairs?.count ?? 0)
      }
      return answers[item.id] != nil
    }
  }

  // MARK: - 提交

  private func submitRead() {
    submitNow(pct: score, answers: nil)
  }

  private func submit() {
    guard let lesson else { return }
    let packed: [[String: AnyEncodable]] = lesson.items.map { item in
      if item.kind == "match" {
        return [
          "id": AnyEncodable(item.id),
          "matched_ids": AnyEncodable(matchAnswers[item.id] ?? []),
          "match_misses": AnyEncodable(matchMisses[item.id] ?? 0),
        ]
      }
      return ["id": AnyEncodable(item.id), "picked": AnyEncodable(answers[item.id] ?? -1)]
    }
    submitNow(pct: 0, answers: packed)
  }

  private func submitNow(pct: Int, answers: [[String: AnyEncodable]]?) {
    guard let client = appState.client else { return }
    submitting = true
    Task {
      defer { submitting = false }
      do {
        result = try await client.submitLesson(
          song.songID, unit: unitID, skill: skill,
          attemptID: UUID().uuidString, pct: pct, answers: answers)
      } catch {
        self.error = error.localizedDescription
      }
    }
  }

  private func load() async {
    guard let client = appState.client else { return }
    do {
      lesson = review
        ? try await client.learnReview(song.songID)
        : try await client.learnLesson(song.songID, unit: unitID, skill: skill)
      if let lesson, lesson.items.isEmpty, lesson.play_mode == nil {
        error = "这个技能暂时没有题目"
      }
    } catch {
      self.error = error.localizedDescription
    }
  }
}
