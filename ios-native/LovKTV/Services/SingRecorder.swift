import AVFoundation
import Foundation

/// 跟唱录音：AVAudioRecorder 录到 tmp wav，按句切分文件，按 RMS 算“唱没唱”。
@MainActor
@Observable
final class SingRecorder {
  private(set) var recording = false
  private(set) var level: Float = 0
  private var recorder: AVAudioRecorder?
  private var meterTimer: Task<Void, Never>?

  enum RecordError: LocalizedError {
    case permissionDenied, engineFailed
    var errorDescription: String? {
      switch self {
      case .permissionDenied: return "请在系统设置里允许麦克风"
      case .engineFailed: return "录音启动失败"
      }
    }
  }

  /// 申请权限并开始录音到指定文件。
  func start(to url: URL) async throws {
    let granted = await AVAudioApplication.requestRecordPermission()
    guard granted else { throw RecordError.permissionDenied }
    let session = AVAudioSession.sharedInstance()
    try session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker, .allowBluetoothHFP])
    try session.setActive(true)
    let settings: [String: Any] = [
      AVFormatIDKey: Int(kAudioFormatLinearPCM),
      AVSampleRateKey: 16000.0,
      AVNumberOfChannelsKey: 1,
      AVLinearPCMBitDepthKey: 16,
      AVLinearPCMIsBigEndianKey: false,
      AVLinearPCMIsFloatKey: false,
    ]
    recorder = try AVAudioRecorder(url: url, settings: settings)
    guard recorder?.record() == true else { throw RecordError.engineFailed }
    recorder?.isMeteringEnabled = true
    recording = true
    meterTimer?.cancel()
    meterTimer = Task { [weak self] in
      while !Task.isCancelled {
        self?.recorder?.updateMeters()
        self?.level = self?.recorder?.averagePower(forChannel: 0) ?? -160
        try? await Task.sleep(for: .milliseconds(80))
      }
    }
  }

  /// 停录并返回分贝数组（粗略按段算 RMS）。
  func stop() -> URL? {
    meterTimer?.cancel()
    recorder?.stop()
    recording = false
    let url = recorder?.url
    recorder = nil
    try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    return url
  }

  /// 从 wav 文件按帧窗口粗算覆盖率：多少帧能量超过阈值。
  /// 返回 (覆盖率 0-1, 平均 dB)。简化版，够判定“有没有唱”。
  static func score(file: URL) -> Double {
    guard let data = try? Data(contentsOf: file), data.count > 44 else { return 0 }
    // WAV 16bit PCM mono；跳过 44 字节头
    let pcm = data.dropFirst(44)
    let frameBytes = 1600 // 100ms @16kHz
    var above = 0
    var frames = 0
    pcm.withUnsafeBytes { raw in
      let samples = raw.bindMemory(to: Int16.self)
      var i = 0
      while i + frameBytes / 2 <= samples.count {
        var sum: Double = 0
        for j in 0..<(frameBytes / 2) {
          let v = Double(samples[i + j]) / 32768.0
          sum += v * v
        }
        let rms = sqrt(sum / Double(frameBytes / 2))
        if rms > 0.02 { above += 1 }
        frames += 1
        i += frameBytes / 2
      }
    }
    return frames > 0 ? Double(above) / Double(frames) : 0
  }
}
