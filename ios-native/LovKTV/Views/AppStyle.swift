import SwiftUI
import UIKit

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

  /// 全页面统一强调色：所有可点控件的主色都用它（tint / 高亮）。
  static var accentColor: Color { pink }

  static var accent: LinearGradient {
    LinearGradient(colors: [pink, violet, cyan],
                   startPoint: .leading, endPoint: .trailing)
  }
  static var accentVertical: LinearGradient {
    LinearGradient(colors: [violet, pink, amber],
                   startPoint: .topLeading, endPoint: .bottomTrailing)
  }
}

// MARK: - 尺寸令牌：全页面统一的间距 / 圆角 / 控件尺寸

enum KTVLayout {
  static let margin: CGFloat = 16        // 页面左右边距
  static let cardRadius: CGFloat = 16    // 卡片圆角
  static let rowRadius: CGFloat = 12     // 行内高亮圆角
  static let artSize: CGFloat = 44       // 行内封面
  static let artNowSize: CGFloat = 56    // 正在唱封面
  static let hitTarget: CGFloat = 44     // 最小点击区域
  static let chipHeight: CGFloat = 30    // 胶囊按钮高度
}

// MARK: - 触觉反馈（轻，不上 UIImpactGenerator 重档位）

@MainActor
enum KTVHaptics {
  static func tap() {
    UIImpactFeedbackGenerator(style: .light).impactOccurred()
  }
  static func select() {
    UISelectionFeedbackGenerator().selectionChanged()
  }
}

// MARK: - 按压反馈：所有自定义按钮统一用它，按下去立即缩 4%

struct KTVPressStyle: ButtonStyle {
  func makeBody(configuration: Configuration) -> some View {
    configuration.label
      .opacity(configuration.isPressed ? 0.75 : 1)
      .scaleEffect(configuration.isPressed ? 0.96 : 1)
      .animation(.spring(duration: 0.18), value: configuration.isPressed)
  }
}

extension ButtonStyle where Self == KTVPressStyle {
  static var ktvPress: KTVPressStyle { KTVPressStyle() }
}

// MARK: - 全局背景：深黑 + 顶部微光

struct KTVBackground: View {
  var body: some View {
    ZStack {
      KTV.bg.ignoresSafeArea()
      // 顶部的紫粉光晕，像包厢顶灯
      EllipticalGradient(colors: [KTV.violet.opacity(0.22), .clear],
                         center: .top, startRadiusFraction: 0, endRadiusFraction: 0.55)
        .ignoresSafeArea()
        .allowsHitTesting(false)
    }
  }
}

// MARK: - 玻璃卡片：轻量底 + 细描边，全页面同一套

struct GlassCard<Content: View>: View {
  var padding: CGFloat = 14
  var radius: CGFloat = KTVLayout.cardRadius
  @ViewBuilder var content: () -> Content
  var body: some View {
    content()
      .padding(padding)
      .background {
        RoundedRectangle(cornerRadius: radius, style: .continuous)
          .fill(KTV.card.opacity(0.82))
          .overlay {
            RoundedRectangle(cornerRadius: radius, style: .continuous)
              .stroke(LinearGradient(colors: [KTV.pink.opacity(0.22), KTV.cyan.opacity(0.10)],
                                     startPoint: .topLeading, endPoint: .bottomTrailing),
                      lineWidth: 1)
          }
          .shadow(color: .black.opacity(0.28), radius: 12, y: 4)
      }
  }
}

// MARK: - 霓虹徽标

struct NeonTag: View {
  let text: String
  var color: Color = KTV.accentColor
  var body: some View {
    Text(text)
      .font(.caption2.weight(.bold))
      .padding(.horizontal, 8).padding(.vertical, 3)
      .background(color.opacity(0.20), in: Capsule())
      .overlay(Capsule().stroke(color.opacity(0.45), lineWidth: 1))
      .foregroundStyle(color)
  }
}

// MARK: - 分段条：曲库入库/在线、点歌台面板统一一种画法

struct SegBar<Item: Hashable>: View {
  let items: [Item]
  @Binding var selection: Item
  var title: (Item) -> String
  var badge: (Item) -> Int? = { _ in nil }
  var disabled: (Item) -> Bool = { _ in false }

  var body: some View {
    HStack(spacing: 4) {
      ForEach(items, id: \.self) { item in
        Button {
          if selection != item {
            KTVHaptics.select()
            selection = item
          }
        } label: {
          HStack(spacing: 4) {
            Text(title(item))
            if let n = badge(item), n > 0 {
              Text("\(n)")
                .font(.caption2.monospacedDigit().weight(.bold))
                .foregroundStyle(selection == item ? Color.white.opacity(0.9) : KTV.accentColor)
            }
          }
          .font(.subheadline.weight(.semibold))
          .frame(maxWidth: .infinity)
          .padding(.vertical, 7)
          .background {
            if selection == item {
              RoundedRectangle(cornerRadius: 8, style: .continuous).fill(KTV.accent)
            }
          }
          .foregroundStyle(selection == item ? Color.white : Color.white.opacity(0.6))
        }
        .buttonStyle(.ktvPress)
        .disabled(disabled(item))
        .opacity(disabled(item) ? 0.35 : 1)
        .accessibilityLabel("切到\(title(item))")
        .accessibilityAddTraits(selection == item ? .isSelected : [])
      }
    }
    .padding(4)
    .background(KTV.cardSoft.opacity(0.7), in: RoundedRectangle(cornerRadius: 11, style: .continuous))
  }
}

// MARK: - 胶囊按钮（点歌 / 入库 / 去曲库这类行内动作统一）

struct ChipButton: View {
  enum Style { case filled, tinted, ghost }
  let title: String
  var icon: String? = nil
  var style: Style = .tinted
  var tint: Color = KTV.accentColor
  var action: () -> Void

  var body: some View {
    Button(action: action) {
      HStack(spacing: 4) {
        if let icon { Image(systemName: icon).font(.caption.weight(.bold)) }
        Text(title)
      }
      .font(.subheadline.weight(.semibold))
      .padding(.horizontal, 14)
      .frame(minHeight: KTVLayout.chipHeight)
      .background {
        Capsule().fill(backgroundFill)
      }
      .overlay(Capsule().stroke(borderColor, lineWidth: 1))
      .foregroundStyle(foregroundColor)
      .contentTransition(.symbolEffect(.replace))
    }
    .buttonStyle(.ktvPress)
  }

  private var backgroundFill: AnyShapeStyle {
    switch style {
    case .filled: return AnyShapeStyle(KTV.accent)
    case .tinted: return AnyShapeStyle(tint.opacity(0.16))
    case .ghost: return AnyShapeStyle(Color.clear)
    }
  }
  private var borderColor: Color {
    switch style {
    case .filled: return .clear
    case .tinted: return tint.opacity(0.35)
    case .ghost: return Color.secondary.opacity(0.3)
    }
  }
  private var foregroundColor: Color {
    switch style {
    case .filled: return .white
    case .tinted: return tint
    case .ghost: return .secondary
    }
  }
}

/// 旧名保留：页面级主按钮
typealias PillButton = ChipButton

// MARK: - 点歌台动作钮（now-act）：图标+小字，主/次两级

struct NowActButton: View {
  let icon: String
  let label: String
  var active = false      // 高亮态（伴奏开/音量面板展开等）
  var prominent = false   // 主按钮：渐变底白字
  var action: () -> Void

  var body: some View {
    Button(action: action) {
      VStack(spacing: 4) {
        Image(systemName: icon)
          .font(.system(size: prominent ? 19 : 17, weight: .semibold))
          .contentTransition(.symbolEffect(.replace))
        Text(label)
          .font(.caption2.weight(.medium))
      }
      .frame(maxWidth: .infinity)
      .frame(minHeight: 52)
      .foregroundStyle(prominent ? Color.white
                       : active ? KTV.accentColor
                       : Color.white.opacity(0.72))
      .background {
        if prominent {
          RoundedRectangle(cornerRadius: 13, style: .continuous)
            .fill(KTV.accent)
            .shadow(color: KTV.pink.opacity(0.35), radius: 8, y: 3)
        } else if active {
          RoundedRectangle(cornerRadius: 13, style: .continuous)
            .fill(KTV.accentColor.opacity(0.14))
            .overlay(RoundedRectangle(cornerRadius: 13, style: .continuous)
              .stroke(KTV.accentColor.opacity(0.4), lineWidth: 1))
        } else {
          RoundedRectangle(cornerRadius: 13, style: .continuous)
            .fill(Color.white.opacity(0.055))
        }
      }
    }
    .buttonStyle(.ktvPress)
  }
}

// MARK: - 图标圆钮（队列行内"唱这首/置顶/试听"统一 30pt）

struct IconCircleButton: View {
  let icon: String
  var tint: Color = KTV.accentColor
  var size: CGFloat = 30
  var filled = true
  var action: () -> Void

  var body: some View {
    Button(action: action) {
      Image(systemName: icon)
        .font(.system(size: size * 0.52, weight: .semibold))
        .foregroundStyle(tint)
        .frame(width: KTVLayout.hitTarget * 0.78, height: KTVLayout.hitTarget * 0.78)
        .contentShape(Rectangle())
        .contentTransition(.symbolEffect(.replace))
    }
    .buttonStyle(.ktvPress)
  }
}

// MARK: - 大圆钮（听歌页播放器主控）

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
        .overlay(Circle().stroke(tint.opacity(0.45), lineWidth: 1.5))
        .foregroundStyle(tint)
        .shadow(color: tint.opacity(0.25), radius: 8)
        .contentTransition(.symbolEffect(.replace))
    }
    .buttonStyle(.ktvPress)
  }
}

// MARK: - 搜索输入条（点歌台曲库/在线复用）

struct SearchField: View {
  @Binding var text: String
  var placeholder: String
  @FocusState private var focused: Bool

  var body: some View {
    HStack(spacing: 8) {
      Image(systemName: "magnifyingglass")
        .font(.subheadline)
        .foregroundStyle(.secondary)
      TextField(placeholder, text: $text)
        .textInputAutocapitalization(.never)
        .autocorrectionDisabled()
        .submitLabel(.search)
        .focused($focused)
      if !text.isEmpty {
        Button {
          text = ""
        } label: {
          Image(systemName: "xmark.circle.fill")
            .foregroundStyle(.secondary)
        }
        .buttonStyle(.ktvPress)
        .accessibilityLabel("清空")
      }
    }
    .padding(.horizontal, 12)
    .frame(minHeight: 38)
    .background(KTV.cardSoft.opacity(0.85), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous)
      .stroke(focused ? KTV.accentColor.opacity(0.5) : .clear, lineWidth: 1))
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
  var size: CGFloat = KTVLayout.artSize
  /// 封面 URL；nil 退回渐变占位（对齐网页 songArt 的 has-img 渐进显示）
  var url: URL? = nil

  var body: some View {
    ZStack {
      LinearGradient(colors: ArtPalette.colors(for: seed),
                     startPoint: .topLeading, endPoint: .bottomTrailing)
      Text(String(seed.trimmingCharacters(in: .whitespaces).first ?? "♪"))
        .font(.system(size: size * 0.5, weight: .semibold, design: .rounded))
        .foregroundStyle(.white.opacity(0.95))
      if let url {
        AsyncImage(url: url) { phase in
          switch phase {
          case .success(let image):
            image.resizable().aspectRatio(contentMode: .fill)
          default:
            Color.clear
          }
        }
        .transition(.opacity)
      }
    }
    .frame(width: size, height: size)
    .clipShape(RoundedRectangle(cornerRadius: size * 0.26, style: .continuous))
  }
}

// MARK: - 霓虹发光封面（听歌页大图，收敛发光范围）

struct GlowArtView: View {
  let seed: String
  var size: CGFloat = 140
  var body: some View {
    ZStack {
      LinearGradient(colors: ArtPalette.colors(for: seed),
                     startPoint: .topLeading, endPoint: .bottomTrailing)
        .blur(radius: 24)
        .opacity(0.45)
        .frame(width: size, height: size)
      ArtView(seed: seed, size: size)
    }
  }
}

// MARK: - 歌曲行（曲库/歌单共用）：封面 + 标题 + 状态 + 点歌 + 更多

struct SongRow: View {
  let song: Song
  /// 封面 URL（nil 时渐变占位）
  var coverURL: URL? = nil
  var showsEnqueue = false
  var showsFavorite = false
  var onEnqueue: (() -> Void)?
  var onFavorite: (() -> Void)?
  var onMore: (() -> Void)?
  var enqueued = false

  var body: some View {
    HStack(spacing: 12) {
      ArtView(seed: song.displayTitle, url: coverURL)
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
        ChipButton(title: enqueued ? "已点" : "点歌",
                   icon: enqueued ? "checkmark" : "plus",
                   style: .tinted,
                   tint: enqueued ? KTV.lime : KTV.accentColor) {
          if !enqueued { onEnqueue?() }
        }
        .disabled(enqueued || !song.isReady)
      }
      if showsFavorite {
        IconCircleButton(icon: song.favorite == true ? "star.fill" : "star",
                         tint: song.favorite == true ? KTV.amber : .secondary,
                         filled: false) {
          onFavorite?()
        }
        .accessibilityLabel(song.favorite == true ? "取消收藏" : "收藏")
      }
      IconCircleButton(icon: "ellipsis", tint: .secondary, filled: false) {
        onMore?()
      }
      .accessibilityLabel("更多")
    }
    .padding(.horizontal, 12).padding(.vertical, 8)
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
      IconCircleButton(icon: "xmark.circle.fill", tint: .secondary, filled: false) {
        onStop()
      }
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
        Text("连接自己的服务器或官方服务后，在这里点歌遥控包厢。")
          .font(.subheadline)
          .foregroundStyle(.secondary)
          .multilineTextAlignment(.center)
      }
      ChipButton(title: "去连接", style: .filled, action: onConnect)
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
      .tint(KTV.accentColor)
      Image(systemName: "speaker.wave.3.fill").foregroundStyle(.secondary)
    }
    .accessibilityElement(children: .combine)
    .accessibilityLabel("音量")
    .accessibilityValue("\(Int(volume))")
  }
}

extension Array {
  subscript(safe index: Int) -> Element? {
    indices.contains(index) ? self[index] : nil
  }
}
