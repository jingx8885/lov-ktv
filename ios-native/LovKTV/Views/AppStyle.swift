import SwiftUI

// MARK: - 主题：KTV 霓虹

enum KTV {
  // 品牌主色：品红→紫罗兰→青
  static let pink = Color(hex: "#ff4d8d")
  static let violet = Color(hex: "#8e2de2")
  static let cyan = Color(hex: "#00d4ff")
  static let lime = Color(hex: "#48dca0")
  static let amber = Color(hex: "#f5c16c")
  static let bg = Color(hex: "#0a0a14")
  static let card = Color(hex: "#14141f")
  static let cardSoft = Color(hex: "#1a1a2a")

  static var accent: LinearGradient {
    LinearGradient(colors: [pink, violet, cyan],
                   startPoint: .leading, endPoint: .trailing)
  }
  static var accentVertical: LinearGradient {
    LinearGradient(colors: [violet, pink, amber],
                   startPoint: .topLeading, endPoint: .bottomTrailing)
  }
  static var glass: some ShapeStyle {
    .ultraThinMaterial
  }
}

// MARK: - 全局背景：深黑 + 顶部微光

struct KTVBackground: View {
  var body: some View {
    ZStack {
      KTV.bg.ignoresSafeArea()
      // 顶部的紫粉光晕，像包厢顶灯
      EllipticalGradient(colors: [KTV.violet.opacity(0.28), .clear],
                         center: .top, startRadiusFraction: 0, endRadiusFraction: 0.6)
        .ignoresSafeArea()
        .allowsHitTesting(false)
    }
  }
}

// MARK: - 玻璃卡片

struct GlassCard<Content: View>: View {
  var padding: CGFloat = 16
  var radius: CGFloat = 20
  @ViewBuilder var content: () -> Content
  var body: some View {
    content()
      .padding(padding)
      .background {
        RoundedRectangle(cornerRadius: radius, style: .continuous)
          .fill(KTV.card.opacity(0.85))
          .overlay {
            RoundedRectangle(cornerRadius: radius, style: .continuous)
              .stroke(LinearGradient(colors: [KTV.pink.opacity(0.25), KTV.cyan.opacity(0.12)],
                                     startPoint: .topLeading, endPoint: .bottomTrailing),
                      lineWidth: 1)
          }
          .shadow(color: .black.opacity(0.35), radius: 16, y: 6)
      }
  }
}

// MARK: - 霓虹徽标

struct NeonTag: View {
  let text: String
  var color: Color = .accentColor
  var body: some View {
    Text(text)
      .font(.caption2.weight(.bold))
      .padding(.horizontal, 8).padding(.vertical, 3)
      .background(color.opacity(0.22), in: Capsule())
      .overlay(Capsule().stroke(color.opacity(0.5), lineWidth: 1))
      .foregroundStyle(color)
      .shadow(color: color.opacity(0.35), radius: 4)
  }
}

// MARK: - 大圆钮（播放/切歌）

struct BigRoundButton: View {
  let icon: String
  var tint: Color = .white
  var size: CGFloat = 64
  var action: () -> Void
  var body: some View {
    Button(action: action) {
      Image(systemName: icon)
        .font(.system(size: size * 0.38, weight: .semibold))
        .frame(width: size, height: size)
        .background(Circle().fill(tint.opacity(0.14)))
        .overlay(Circle().stroke(tint.opacity(0.5), lineWidth: 1.5))
        .foregroundStyle(tint)
        .shadow(color: tint.opacity(0.3), radius: 8)
    }
    .buttonStyle(.plain)
    .contentTransition(.symbolEffect(.replace))
  }
}

// MARK: - 胶囊按钮

struct PillButton: View {
  let title: String
  var filled = false
  var tint: Color = .accentColor
  var action: () -> Void
  var body: some View {
    Button(action: action) {
      Text(title)
        .font(.subheadline.weight(.semibold))
        .padding(.horizontal, 18).padding(.vertical, 9)
        .background(filled ? AnyShapeStyle(KTV.accent) : AnyShapeStyle(tint.opacity(0.16)),
                    in: Capsule())
        .overlay(Capsule().stroke(filled ? .clear : tint.opacity(0.4), lineWidth: 1))
        .foregroundStyle(filled ? .white : tint)
    }
    .buttonStyle(.plain)
  }
}

// MARK: - 封面（保留原哈希调色板）

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
    .shadow(color: .black.opacity(0.3), radius: 4, y: 2)
  }
}

// MARK: - 霓虹发光封面（正在播放大图）

struct GlowArtView: View {
  let seed: String
  var size: CGFloat = 140
  var body: some View {
    ZStack {
      // 背后光晕
      LinearGradient(colors: ArtPalette.colors(for: seed),
                     startPoint: .topLeading, endPoint: .bottomTrailing)
        .blur(radius: 30)
        .opacity(0.55)
        .frame(width: size, height: size)
      ArtView(seed: seed, size: size)
    }
  }
}

// MARK: - 歌曲行（玻璃风）

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
            NeonTag(text: badge.text,
                    color: badge.isError ? .red : .orange)
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
          .tint(enqueued ? KTV.lime : .accentColor)
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

// MARK: - Toast

struct ToastView: View {
  let message: String
  var body: some View {
    Text(message)
      .font(.subheadline.weight(.medium))
      .padding(.horizontal, 16).padding(.vertical, 10)
      .background(.ultraThinMaterial, in: Capsule())
      .overlay(Capsule().stroke(KTV.accent, lineWidth: 1))
      .shadow(radius: 12, y: 4)
      .transition(.move(edge: .top).combined(with: .opacity))
      .accessibilityLabel("提示：\(message)")
  }
}

// MARK: - 试听条

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

// MARK: - 未连接

struct NotConnectedView: View {
  var onConnect: () -> Void
  var body: some View {
    VStack(spacing: 24) {
      Image("Mascot")
        .resizable().aspectRatio(contentMode: .fit)
        .frame(width: 160)
        .shadow(color: KTV.violet.opacity(0.4), radius: 16)
      VStack(spacing: 8) {
        Text("还没连上")
          .font(.title3.weight(.semibold))
        Text("连接自己的服务器或官方服务后，在这里遥控包厢。")
          .font(.subheadline)
          .foregroundStyle(.secondary)
          .multilineTextAlignment(.center)
      }
      PillButton(title: "去连接", filled: true, action: onConnect)
    }
    .padding(32)
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }
}

// MARK: - 音量条

struct VolumeRow: View {
  let volume: Double
  let onCommit: (Double) -> Void
  @State private var editing = false
  @State private var draft: Double = 0

  var body: some View {
    HStack(spacing: 12) {
      Image(systemName: "speaker.fill").foregroundStyle(.secondary)
      Slider(value: Binding(
        get: { editing ? draft : volume },
        set: { draft = $0; editing = true }),
        in: 0...100, step: 1) { editing in
        if !editing { onCommit(draft); self.editing = false }
      }
      .tint(KTV.pink)
      Image(systemName: "speaker.wave.3.fill").foregroundStyle(.secondary)
    }
    .accessibilityElement(children: .combine)
    .accessibilityLabel("音量")
    .accessibilityValue("\(Int(volume))")
  }
}
