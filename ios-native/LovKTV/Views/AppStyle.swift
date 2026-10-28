import SwiftUI

/// 封面占位：用标题哈希出一对渐变颜色，与网页端 PALETTE 同源。
enum ArtPalette {
  private static let pairs: [(String, String)] = [
    ("#ff5f6d", "#ffc371"), ("#5f72ff", "#9b5cff"),
    ("#00b4db", "#0083b0"), ("#f7971e", "#ffd200"),
    ("#11998e", "#38ef7d"), ("#ee0979", "#ff6a00"),
    ("#8e2de2", "#ff4b8b"), ("#4facfe", "#00f2fe"),
  ]
  static func colors(for seed: String) -> [Color] {
    var hash: UInt32 = 0
    for scalar in seed.unicodeScalars { hash = (hash &* 31 &+ scalar.value) }
    let (a, b) = pairs[Int(hash % UInt32(pairs.count))]
    return [Color(hex: a), Color(hex: b)]
  }
}

extension Color {
  init(hex: String) {
    var value = hex
    if value.hasPrefix("#") { value.removeFirst() }
    let rgb = UInt64(value, radix: 16) ?? 0
    self.init(red: Double((rgb >> 16) & 0xff) / 255,
              green: Double((rgb >> 8) & 0xff) / 255,
              blue: Double(rgb & 0xff) / 255)
  }
}

struct ArtView: View {
  let seed: String
  var size: CGFloat = 44
  var body: some View {
    ZStack {
      LinearGradient(colors: ArtPalette.colors(for: seed),
                     startPoint: .topLeading, endPoint: .bottomTrailing)
      Text(String(seed.trimmingCharacters(in: .whitespaces).first ?? "♪"))
        .font(.system(size: size * 0.5, weight: .semibold, design: .rounded))
        .foregroundStyle(.white.opacity(0.95))
    }
    .frame(width: size, height: size)
    .clipShape(RoundedRectangle(cornerRadius: size * 0.28, style: .continuous))
  }
}

/// 曲库 / 队列行：封面 + 标题 + 状态徽标 + 可选操作按钮 + 更多菜单。
struct SongRow: View {
  let song: Song
  var showsEnqueue = false
  var onEnqueue: (() -> Void)?
  var onMore: (() -> Void)?
  var enqueued = false

  var body: some View {
    HStack(spacing: 12) {
      ArtView(seed: song.displayTitle)
      VStack(alignment: .leading, spacing: 3) {
        Text(song.displayTitle)
          .font(.body.weight(.medium))
          .lineLimit(1)
        HStack(spacing: 6) {
          if let badge = song.badge {
            Text(badge.text)
              .font(.caption2.weight(.semibold))
              .padding(.horizontal, 6).padding(.vertical, 2)
              .background(badge.isError ? Color.red.opacity(0.18) : Color.orange.opacity(0.18),
                          in: Capsule())
              .foregroundStyle(badge.isError ? .red : .orange)
          }
          Text(song.displayArtist)
            .font(.caption)
            .foregroundStyle(.secondary)
            .lineLimit(1)
        }
      }
      Spacer(minLength: 8)
      if showsEnqueue {
        Button(enqueued ? "已点" : "点歌") { onEnqueue?() }
          .buttonStyle(.borderedProminent)
          .tint(enqueued ? .green : .accentColor)
          .buttonBorderShape(.capsule)
          .disabled(enqueued || !song.isReady)
      }
      Button { onMore?() } label: {
        Image(systemName: "ellipsis")
          .font(.body.weight(.semibold))
          .foregroundStyle(.secondary)
          .frame(width: 30, height: 30)
      }
      .buttonStyle(.plain)
    }
    .padding(.horizontal, 14).padding(.vertical, 10)
    .contentShape(Rectangle())
  }
}

/// 顶部 Toast：statusMessage 变化时淡入，AppState 负责 2.8s 后清除。
struct ToastView: View {
  let message: String
  var body: some View {
    Text(message)
      .font(.subheadline.weight(.medium))
      .padding(.horizontal, 16).padding(.vertical, 10)
      .background(.ultraThinMaterial, in: Capsule())
      .shadow(radius: 8, y: 4)
      .transition(.move(edge: .top).combined(with: .opacity))
      .accessibilityLabel("提示：\(message)")
  }
}

/// 试听迷你条：显示在 TabView 上方。
struct ListeningBar: View {
  @Bindable var player: PreviewPlayer
  var title: String?
  var onStop: () -> Void

  var body: some View {
    HStack(spacing: 12) {
      ArtView(seed: title ?? "♪", size: 36)
      VStack(alignment: .leading, spacing: 2) {
        Text(title ?? "正在下载…")
          .font(.subheadline.weight(.medium)).lineLimit(1)
        Text(player.downloading ? "正在下载…" : "正在手机播放，可锁屏收听")
          .font(.caption).foregroundStyle(.secondary)
      }
      Spacer()
      if player.downloading { ProgressView() }
      Button { onStop() } label: {
        Image(systemName: "xmark.circle.fill")
          .font(.title3)
          .foregroundStyle(.secondary)
      }
      .buttonStyle(.plain)
      .accessibilityLabel("停止试听")
    }
    .padding(.horizontal, 14).padding(.vertical, 8)
    .background(.ultraThinMaterial)
    .overlay(alignment: .top) { Divider() }
  }
}

/// 未连接占位
struct NotConnectedView: View {
  var onConnect: () -> Void
  var body: some View {
    ContentUnavailableView {
      Label("未连接", systemImage: "dot.radiowaves.left.and.right")
    } description: {
      Text("连接自己的服务器或官方服务后，在这里遥控包厢。")
    } actions: {
      Button("去连接", action: onConnect)
        .buttonStyle(.borderedProminent)
    }
  }
}
