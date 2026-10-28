import AVFoundation
import Foundation
import MediaPlayer

/// 手机试听：下载服务器 local 音频后用 AVAudioPlayer 播放，注册 NowPlaying 与遥控。
@MainActor
@Observable
final class PreviewPlayer: NSObject {
  private(set) var playingID: String?
  private(set) var downloading = false
  private var player: AVAudioPlayer?
  private var tempFile: URL?

  override init() {
    super.init()
    NotificationCenter.default.addObserver(self, selector: #selector(interrupted),
                                           name: AVAudioSession.interruptionNotification, object: nil)
    NotificationCenter.default.addObserver(self, selector: #selector(routeChanged),
                                           name: AVAudioSession.routeChangeNotification, object: nil)
  }

  func toggle(song: Song, client: LovKTVClient?) async -> String? {
    if playingID == song.songID { stop(); return nil }
    return await play(song: song, client: client)
  }

  func play(song: Song, client: LovKTVClient?) async -> String? {
    guard let client, song.isReady else { return "请先连接服务器" }
    stop()
    downloading = true
    defer { downloading = false }
    do {
      let file = try await client.downloadPreview(songID: song.songID)
      let data = try Data(contentsOf: file)
      tempFile = file
      try AVAudioSession.sharedInstance().setCategory(.playback, mode: .default)
      try AVAudioSession.sharedInstance().setActive(true)
      let player = try AVAudioPlayer(data: data)
      player.delegate = self
      self.player = player
      playingID = song.songID
      player.play()
      MPNowPlayingInfoCenter.default().nowPlayingInfo = [
        MPMediaItemPropertyTitle: song.displayTitle,
        MPMediaItemPropertyArtist: song.displayArtist,
        MPMediaItemPropertyAlbumTitle: "LovKTV 服务器试听",
      ]
      let center = MPRemoteCommandCenter.shared()
      center.pauseCommand.addTarget { [weak self] _ in
        self?.player?.pause(); return .success
      }
      center.playCommand.addTarget { [weak self] _ in
        self?.player?.play(); return .success
      }
      return nil
    } catch {
      stop()
      return (error as? LocalizedError)?.errorDescription ?? "无法试听：需服务器本地音频"
    }
  }

  func stop() {
    player?.stop()
    player = nil
    playingID = nil
    MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
    let center = MPRemoteCommandCenter.shared()
    center.pauseCommand.removeTarget(nil)
    center.playCommand.removeTarget(nil)
    try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    if let tempFile { try? FileManager.default.removeItem(at: tempFile) }
    tempFile = nil
  }

  @objc private func interrupted() { player?.pause() }
  @objc private func routeChanged(_ note: Notification) {
    guard let reason = note.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt,
          reason == AVAudioSession.RouteChangeReason.oldDeviceUnavailable.rawValue else { return }
    player?.pause()
  }
}

extension PreviewPlayer: AVAudioPlayerDelegate {
  nonisolated func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
    Task { @MainActor in self.stop() }
  }
}
