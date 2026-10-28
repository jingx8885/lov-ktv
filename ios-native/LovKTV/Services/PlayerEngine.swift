import AVFoundation
import Foundation
import MediaPlayer

/// 听歌播放器：AVPlayer 流式播放 + 卡拉OK时间轴高亮。
/// 原唱 original.mp3 / 伴奏 instrumental.wav 两个轨随时切换。
@MainActor
@Observable
final class PlayerEngine {
  private(set) var songID: String?
  private(set) var track: Track = .original
  private(set) var playing = false
  private(set) var currentMS = 0
  private(set) var durationMS = 0
  private(set) var timeline: LyricsTimeline?
  private(set) var loading = false
  private(set) var detail: SongDetail?

  private var player: AVPlayer?
  private var timeObserver: Any?
  private var client: LovKTVClient?

  enum Track: String { case original, accompaniment }

  var activeIndex: Int? { timeline?.activeIndex(at: currentMS) }
  var canAccompaniment: Bool { detail?.hasInstrumental == true }

  /// 打开一首歌：取详情→时间轴→起播原唱。
  func open(song: Song, client: LovKTVClient) async -> String? {
    stop()
    self.client = client
    songID = song.songID
    detail = nil
    timeline = nil
    loading = true
    defer { loading = false }
    do {
      let d = try await client.songDetail(song.songID)
      detail = d
    } catch {
      detail = nil
    }
    timeline = await client.fetchTimeline(songID: song.songID)
    return await startPlayback(track: .original)
  }

  /// 切原唱/伴奏轨；伴奏不存在时给提示。
  func setTrack(_ next: Track) async -> String? {
    guard next != track else { return nil }
    if next == .accompaniment, detail?.hasInstrumental != true {
      return "这首歌还没有伴奏轨"
    }
    return await startPlayback(track: next)
  }

  private func startPlayback(track: Track) async -> String? {
    guard let client, let songID else { return "请先连接服务器" }
    let name = track == .original ? "original.mp3" : "instrumental.wav"
    guard let url = await client.mediaURL(songID: songID, name: name) else {
      return "音频地址无效"
    }
    let asset = await client.authorizedAsset(url: url)
    let item = AVPlayerItem(asset: asset)
    if let player {
      player.replaceCurrentItem(with: item)
    } else {
      player = AVPlayer(playerItem: item)
    }
    self.track = track
    durationMS = 0
    addTimeObserver()
    player?.play()
    playing = true
    updateNowPlaying()
    return nil
  }

  private func addTimeObserver() {
    if let player, let timeObserver { player.removeTimeObserver(timeObserver) }
    guard let player else { return }
    timeObserver = player.addPeriodicTimeObserver(
      forInterval: CMTime(seconds: 0.1, preferredTimescale: 30),
      queue: .main
    ) { [weak self] time in
      Task { @MainActor in
        guard let self else { return }
        self.currentMS = Int(time.seconds * 1000)
        if let dur = self.player?.currentItem?.duration.seconds, dur.isFinite {
          self.durationMS = Int(dur * 1000)
        }
      }
    }
  }

  func toggle() {
    if playing { player?.pause() } else { player?.play() }
    playing.toggle()
    updateNowPlaying()
  }

  func seek(to fraction: Double) {
    guard let player, durationMS > 0 else { return }
    let target = CMTime(seconds: Double(durationMS) / 1000 * fraction, preferredTimescale: 30)
    player.seek(to: target, toleranceBefore: .zero, toleranceAfter: .zero) { [weak self] _ in
      Task { @MainActor in self?.currentMS = Int(target.seconds * 1000) }
    }
  }

  /// 精确跳到某毫秒（点唱/跟唱重放一句用）
  func seekMS(_ ms: Int) {
    guard let player else { return }
    player.seek(to: CMTime(seconds: Double(ms) / 1000, preferredTimescale: 600),
                toleranceBefore: .zero, toleranceAfter: .zero)
    currentMS = ms
  }

  /// 只播一句：seek 到 start 并在 end 停（靠 timer 在视图层驱动也行，先给引擎能力）
  func pause() { player?.pause(); playing = false; updateNowPlaying() }
  func resume() { player?.play(); playing = true; updateNowPlaying() }

  func stop() {
    if let player, let timeObserver { player.removeTimeObserver(timeObserver) }
    timeObserver = nil
    player?.pause()
    player = nil
    playing = false
    currentMS = 0
    durationMS = 0
    MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
    MPRemoteCommandCenter.shared().playCommand.removeTarget(nil)
    MPRemoteCommandCenter.shared().pauseCommand.removeTarget(nil)
  }

  private func updateNowPlaying() {
    MPNowPlayingInfoCenter.default().nowPlayingInfo = [
      MPMediaItemPropertyTitle: detail?.displayTitle ?? "LovKTV",
      MPMediaItemPropertyArtist: detail?.displayArtist ?? "",
      MPNowPlayingInfoPropertyPlaybackRate: playing ? 1.0 : 0.0,
    ]
    let center = MPRemoteCommandCenter.shared()
    center.playCommand.addTarget { [weak self] _ in
      self?.player?.play(); self?.playing = true; self?.updateNowPlaying(); return .success
    }
    center.pauseCommand.addTarget { [weak self] _ in
      self?.player?.pause(); self?.playing = false; self?.updateNowPlaying(); return .success
    }
  }
}

/// 在线搜歌的试听流：AVPlayer 直接播 /api/preview/{id}，无需下载。
@MainActor
@Observable
final class StreamPreview {
  private(set) var playingID: String?
  private var player: AVPlayer?

  func play(hit: SearchHit, client: LovKTVClient) async -> String? {
    guard let url = await client.previewURL(hitID: hit.id) else { return "预览地址无效" }
    stop()
    let asset = await client.authorizedAsset(url: url)
    player = AVPlayer(playerItem: AVPlayerItem(asset: asset))
    playingID = hit.id
    player?.play()
    return nil
  }

  func toggle(_ hit: SearchHit, client: LovKTVClient) async -> String? {
    if playingID == hit.id { stop(); return nil }
    return await play(hit: hit, client: client)
  }

  func stop() {
    player?.pause()
    player = nil
    playingID = nil
  }
}
