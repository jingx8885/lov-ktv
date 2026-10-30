import SwiftUI

/// 在线搜结果行：封面(网络图或渐变) + 来源徽标 + 试听/入库。
/// 点歌台"在线"面板与"搜歌"tab 共用。
struct OnlineHitRow: View {
  let hit: SearchHit
  let previewing: Bool
  let imported: Bool
  let onPreview: () -> Void
  let onImport: () -> Void

  var body: some View {
    HStack(spacing: 12) {
      cover
      VStack(alignment: .leading, spacing: 3) {
        Text(hit.displayTitle).font(.body.weight(.medium)).lineLimit(1)
        HStack(spacing: 6) {
          if !hit.sourceLabel.isEmpty {
            Text(hit.sourceLabel)
              .font(.caption2.weight(.semibold))
              .padding(.horizontal, 6).padding(.vertical, 2)
              .background(KTV.accentColor.opacity(0.15), in: Capsule())
              .foregroundStyle(KTV.accentColor)
          }
          if hit.is_mv == true {
            Text("MV")
              .font(.caption2.weight(.semibold))
              .padding(.horizontal, 6).padding(.vertical, 2)
              .background(KTV.violet.opacity(0.18), in: Capsule())
              .foregroundStyle(KTV.violet)
          }
          Text([hit.displayArtist, hit.durationText].filter { !$0.isEmpty }.joined(separator: " · "))
            .font(.caption).foregroundStyle(.secondary).lineLimit(1)
        }
      }
      Spacer(minLength: 8)
      IconCircleButton(
        icon: previewing ? "stop.circle.fill" : "play.circle.fill",
        tint: previewing ? .secondary : KTV.accentColor,
        filled: false,
        action: onPreview)
        .accessibilityLabel(previewing ? "停止试听" : "试听")
      ChipButton(title: imported ? "已入库" : "入库",
                 icon: imported ? "checkmark" : "square.and.arrow.down",
                 style: .tinted,
                 tint: imported ? KTV.lime : KTV.accentColor,
                 action: onImport)
        .disabled(imported)
    }
    .padding(.horizontal, 12).padding(.vertical, 8)
  }

  @ViewBuilder
  private var cover: some View {
    if let pic = hit.pic, let url = URL(string: pic) {
      AsyncImage(url: url) { phase in
        switch phase {
        case .success(let image):
          image.resizable().aspectRatio(contentMode: .fill)
        default:
          ArtView(seed: hit.displayTitle)
        }
      }
      .frame(width: KTVLayout.artSize, height: KTVLayout.artSize)
      .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    } else {
      ArtView(seed: hit.displayTitle)
    }
  }
}
