import SwiftUI

/// 学习页：选歌 → campaign（单元×技能进度）→ lesson（多选/配对/跟读）。
/// 对齐 m.html 点歌台的学习入口；自建服可用，官方服未暴露 learn 接口会提示。
struct LearnView: View {
  @Environment(AppState.self) private var appState
  @Environment(LibraryStore.self) private var library

  var body: some View {
    NavigationStack {
      ZStack {
        KTVBackground()
        if appState.connection == nil {
          ContentUnavailableView {
            Label("未连接", systemImage: "graduationcap")
          } description: {
            Text("先在设置里连接服务器。")
          }
        } else if appState.connection?.mode == .official {
          ContentUnavailableView {
            Label("暂不可用", systemImage: "graduationcap")
          } description: {
            Text("官方服务暂未开放学习接口，连自己的服务器可用。")
          }
        } else {
          songPicker
        }
      }
      .navigationTitle("学习")
      .navigationBarTitleDisplayMode(.inline)
    }
    .task(id: appState.connection) {
          library.client = appState.client
          if library.client != nil { await library.search(page: 1) }
        }
    .onAppear {
          library.client = appState.client
          if library.songs.isEmpty, library.client != nil {
            Task { await library.search(page: 1) }
          }
    }
  }

  @ViewBuilder
  private var songPicker: some View {
    List {
      ForEach(library.songs.filter { $0.isReady }) { song in
        NavigationLink {
          CampaignView(song: song)
        } label: {
          HStack(spacing: 12) {
            ArtView(seed: song.displayTitle, size: 40)
            VStack(alignment: .leading) {
              Text(song.displayTitle).lineLimit(1)
              Text(song.displayArtist).font(.caption).foregroundStyle(.secondary)
            }
          }
        }
      }
      if library.songs.isEmpty {
        ContentUnavailableView("还没有可学的歌", systemImage: "music.note.list",
                               description: Text("先去曲库入库几首歌。"))
        .listRowSeparator(.hidden)
      }
    }
    .listStyle(.plain)
    .scrollContentBackground(.hidden)
  }
}

/// 一首歌的 campaign：目标进度 + 单元×技能格子 + 错题复习
struct LessonDest: Hashable { var unit: String; var skill: String }

struct CampaignView: View {
  @Environment(AppState.self) private var appState
  let song: Song
  @State private var campaign: LearnCampaign?
  @State private var error: String?
  @State private var loading = true
  @State private var practiceEntry: String?
  @State private var lessonDest: LessonDest?

  var body: some View {
    Group {
      if loading {
        ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
      } else if let error {
        ContentUnavailableView("还不能学", systemImage: "text.badge.xmark",
                               description: Text(error))
      } else if let campaign {
        campaignBody(campaign)
      }
    }
    .navigationTitle(song.displayTitle)
    .navigationBarTitleDisplayMode(.inline)
    .navigationDestination(isPresented: Binding(
      get: { practiceEntry != nil },
      set: { if !$0 { practiceEntry = nil } })) {
      PracticeEntryView(song: song)
    }
    .navigationDestination(item: $lessonDest) { dest in
      LessonView(song: song, unitID: dest.unit, skill: dest.skill)
    }
    .task { await load() }
  }

  @ViewBuilder
  private func campaignBody(_ c: LearnCampaign) -> some View {
    List {
      Section("目标") {
        HStack(spacing: 16) {
          goalChip("单词", c.goal.words)
          goalChip("句子", c.goal.sentences)
          goalChip("跟读", c.goal.read)
          if c.mistakes > 0 {
            NavigationLink {
              LessonView(song: song, unitID: "review", skill: "review", review: true)
            } label: {
              Label("错题 \(c.mistakes)", systemImage: "exclamationmark.arrow.circlepath")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.orange)
            }
          }
        }
      }

      Section {
        NavigationLink {
          ReciteView()
        } label: {
          Label("单词本", systemImage: "book.closed")
        }
        NavigationLink {
          SongWordsSetupView(song: song)
        } label: {
          Label("选这首歌的词", systemImage: "character.book.closed")
        }
      }
      Section("单元") {
        ForEach(c.units) { unit in
          VStack(alignment: .leading, spacing: 10) {
            Text("第 \(unit.index + 1) 单元 · \(unit.preview ?? "")")
              .font(.subheadline.weight(.medium))
            HStack(spacing: 8) {
              ForEach(unit.skills) { skill in
                if skill.locked {
                  skillChip(skill, enabled: false)
                } else {
                  Button {
                    if skill.play_mode == "tap" {
                      practiceEntry = "practice"
                    } else {
                      lessonDest = LessonDest(unit: unit.id, skill: skill.id)
                    }
                  } label: {
                    skillChip(skill, enabled: true)
                  }
                  .buttonStyle(.plain)
                }
              }
            }
          }
          .padding(.vertical, 6)
        }
      }
    }
    .listStyle(.insetGrouped)
    .scrollContentBackground(.hidden)
  }

  private func goalChip(_ label: String, _ g: LearnCampaign.DoneTotal) -> some View {
    VStack(spacing: 2) {
      Text("\(g.done)/\(g.total)")
        .font(.headline.monospacedDigit())
      Text(label).font(.caption2).foregroundStyle(.secondary)
    }
    .frame(maxWidth: .infinity)
  }

  private func skillChip(_ skill: LearnCampaign.Skill, enabled: Bool) -> some View {
    VStack(spacing: 2) {
      Text(skill.label).font(.caption.weight(.semibold))
      Text(skill.status == "mastered" ? "已掌握" : skill.status == "passed" ? "\(skill.score)分" : skill.locked ? "🔒" : "开始")
        .font(.caption2)
        .foregroundStyle(skill.status == "passed" || skill.status == "mastered" ? .green : .secondary)
    }
    .frame(maxWidth: .infinity)
    .padding(.vertical, 8)
    .background(skill.locked ? Color.secondary.opacity(0.06) : Color.accentColor.opacity(0.12),
                in: RoundedRectangle(cornerRadius: 10))
    .foregroundStyle(skill.locked ? .secondary : .primary)
  }

  private func load() async {
    guard let client = appState.client else { return }
    do {
      campaign = try await client.learnCampaign(song.songID)
    } catch {
      self.error = error.localizedDescription
    }
    loading = false
  }
}
