import SwiftUI

/// 歌单列表 + 单条歌单的歌。对齐 m.html 歌单管理面。
struct PlaylistsView: View {
  @Environment(AppState.self) private var appState
  @State private var playlists: [Playlist] = []
  @State private var loading = true
  @State private var newName = ""
  @State private var editing: Playlist?
  @State private var confirmDelete: Playlist?
  @State private var error: String?

  var body: some View {
    List {
      Section {
        HStack {
          TextField("新歌单名", text: $newName)
          Button("建") { create() }
            .disabled(newName.trimmingCharacters(in: .whitespaces).isEmpty)
        }
      }
      Section("歌单") {
        ForEach(playlists) { list in
          NavigationLink {
            PlaylistSongsView(playlist: list)
          } label: {
            HStack {
              Text(list.name)
              Spacer()
              Text("\(list.count ?? 0)")
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)
            }
          }
          .swipeActions(edge: .trailing) {
            Button("改名") { editing = list }.tint(.blue)
            Button("删除", role: .destructive) { confirmDelete = list }
          }
        }
        if playlists.isEmpty && !loading {
          Text("还没有歌单").foregroundStyle(.secondary)
        }
      }
    }
    .navigationTitle("歌单")
    .task { await load() }
    .alert("改名", isPresented: .constant(editing != nil), presenting: editing) { list in
      TextField("歌单名", text: Binding(
        get: { list.name },
        set: { editing?.name = $0 }))
      Button("保存") { rename(list) }
      Button("取消", role: .cancel) { editing = nil }
    }
    .alert("删除歌单？", isPresented: .constant(confirmDelete != nil), presenting: confirmDelete) { list in
      Button("删除 \(list.name)", role: .destructive) { remove(list) }
      Button("取消", role: .cancel) { confirmDelete = nil }
    }
  }

  private func load() async {
    guard let client = appState.client else { return }
    playlists = (try? await client.playlists()) ?? []
    loading = false
  }

  private func create() {
    guard let client = appState.client else { return }
    Task {
      do {
        _ = try await client.createPlaylist(name: newName)
        newName = ""
        await load()
      } catch {
        appState.showStatus(error.localizedDescription)
      }
    }
  }

  private func rename(_ list: Playlist) {
    guard let client = appState.client else { return }
    Task {
      _ = try? await client.renamePlaylist(list.id, name: list.name)
      editing = nil
      await load()
    }
  }

  private func remove(_ list: Playlist) {
    guard let client = appState.client else { return }
    Task {
      try? await client.deletePlaylist(list.id)
      confirmDelete = nil
      await load()
    }
  }
}

/// 歌单里的歌：点歌入队或移除
struct PlaylistSongsView: View {
  @Environment(AppState.self) private var appState
  let playlist: Playlist
  @State private var songs: [Song] = []
  @State private var loading = true
  @State private var enqueued: Set<String> = []

  var body: some View {
    List {
      ForEach(songs) { song in
        SongRow(song: song, showsEnqueue: true,
                onEnqueue: { enqueue(song) },
                onMore: nil,
                enqueued: enqueued.contains(song.songID))
        .swipeActions(edge: .trailing) {
          Button("移出", role: .destructive) { remove(song) }
        }
      }
      if songs.isEmpty && !loading {
        Text("这个歌单还没有歌").foregroundStyle(.secondary)
      }
    }
    .navigationTitle(playlist.name)
    .task { await load() }
  }

  private func load() async {
    guard let client = appState.client else { return }
    if let r = try? await client.playlistSongs(playlist.id) {
      songs = r.songs
    }
    loading = false
  }

  private func enqueue(_ song: Song) {
    enqueued.insert(song.songID)
    Task { await appState.enqueue(song: song) }
    Task {
      try? await Task.sleep(for: .milliseconds(1600))
      enqueued.remove(song.songID)
    }
  }

  private func remove(_ song: Song) {
    guard let client = appState.client else { return }
    Task {
      try? await client.playlistRemove(playlist.id, songID: song.songID)
      await load()
    }
  }
}

/// 行内动作"加入歌单"：列出全部歌单 + 新建
struct AddToPlaylistSheet: View {
  @Environment(AppState.self) private var appState
  let song: Song
  @State private var playlists: [Playlist] = []
  @State private var newName = ""
  @State private var loading = true
  @State private var added: Set<String> = []
  @Environment(\.dismiss) private var dismiss

  var body: some View {
    NavigationStack {
      List {
        Section {
          HStack {
            TextField("新歌单名", text: $newName)
            Button("建并加入") { createAndAdd() }
              .disabled(newName.trimmingCharacters(in: .whitespaces).isEmpty)
          }
        }
        Section("加到歌单") {
          ForEach(playlists) { list in
            Button {
              add(to: list)
            } label: {
              HStack {
                Text(list.name).foregroundStyle(.primary)
                Spacer()
                if added.contains(list.id) {
                  Image(systemName: "checkmark").foregroundStyle(.green)
                } else {
                  Text("\(list.count ?? 0)").font(.caption).foregroundStyle(.secondary)
                }
              }
            }
            .disabled(added.contains(list.id))
          }
          if playlists.isEmpty && !loading {
            Text("还没有歌单，先建一个").foregroundStyle(.secondary)
          }
        }
      }
      .navigationTitle("加入歌单")
      .navigationBarTitleDisplayMode(.inline)
      .toolbar {
        ToolbarItem(placement: .topBarTrailing) {
          Button("完成") { dismiss() }
        }
      }
      .task { await load() }
    }
  }

  private func load() async {
    guard let client = appState.client else { return }
    playlists = (try? await client.playlists(songID: song.songID)) ?? []
    added = Set(playlists.filter { ($0.has_song ?? 0) > 0 }.map(\.id))
    loading = false
  }

  private func add(to list: Playlist) {
    guard let client = appState.client else { return }
    Task {
      _ = try? await client.playlistAdd(list.id, songID: song.songID)
      added.insert(list.id)
      appState.showStatus("已加入「\(list.name)」")
    }
  }

  private func createAndAdd() {
    guard let client = appState.client else { return }
    Task {
      do {
        let list = try await client.createPlaylist(name: newName)
        _ = try? await client.playlistAdd(list.id, songID: song.songID)
        added.insert(list.id)
        newName = ""
        appState.showStatus("已建歌单并加入")
        await load()
      } catch {
        appState.showStatus(error.localizedDescription)
      }
    }
  }
}
