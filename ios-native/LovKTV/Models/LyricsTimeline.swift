import Foundation

/// /media/{id}/lyrics.json 的精简模型：逐句 + 逐词时间轴，用于卡拉OK高亮。
/// 字段与网页端 shared/lyrics/js/paint.js 消费的结构保持一致。
struct LyricsTimeline: Decodable, Sendable {
  var cues: [Cue]
  var language: String?

  struct Cue: Decodable, Sendable, Identifiable {
    var id: Int { start_ms }
    var text: String?
    var surface: String?
    var zh: String?
    var translation: String?
    var romaji: String?
    var start_ms: Int
    var end_ms: Int
    var tokens: [Token]?

    var display: String { surface ?? text ?? "" }
    var sub: String? {
      let value = translation ?? zh ?? ""
      return value.isEmpty ? nil : value
    }
  }

  struct Token: Decodable, Sendable {
    var surface: String?
    var text: String?
    var reading: String?
    var romaji: String?
    var translation: String?
    var zh: String?
    var start_ms: Int
    var end_ms: Int
    var display: String { surface ?? text ?? "" }

    var romajiText: String { romaji ?? "" }
    var glossText: String {
      let value = translation ?? zh ?? ""
      return value
    }
    var hasAnno: Bool {
      !romajiText.trimmingCharacters(in: .whitespaces).isEmpty
        || !glossText.trimmingCharacters(in: .whitespaces).isEmpty
    }
  }

  /// 歌词语种归类（与 paint.js lyricScript 一致）
  var script: LyricScript {
    let lang = (language ?? "").trimmingCharacters(in: .whitespaces).lowercased()
    if lang == "ja" || lang.hasPrefix("ja-") { return .ja }
    if lang == "en" || lang.hasPrefix("en-") { return .en }
    if lang == "yue" || lang.hasPrefix("zh") { return .zh }
    return .other(lang)
  }

  /// 当前毫秒所在 cue 的下标
  func activeIndex(at ms: Int) -> Int? {
    cues.firstIndex { ms >= $0.start_ms && ms < $0.end_ms }
      ?? (ms < (cues.first?.start_ms ?? 0) ? 0 : cues.last.map { _ in cues.count - 1 })
  }
}

enum LyricScript: Equatable, Sendable {
  case ja, zh, en
  case other(String)
}

/// 逐词推进度，与 paint.js tokenProgress 一致。
func tokenProgress(start: Int, end: Int, at ms: Int) -> Double {
  if ms >= end { return 1 }
  if ms >= start { return Double(ms - start) / Double(max(end - start, 1)) }
  return 0
}

func isKanaText(_ value: String) -> Bool {
  !value.isEmpty && value.allSatisfy {
    let s = $0.unicodeScalars
    return s.allSatisfy { (0x3040...0x30FF).contains($0.value) }
      || $0 == "ー" || $0 == "ゝ" || $0 == "ゞ"
  }
}

func isKanjiText(_ value: String) -> Bool {
  value.unicodeScalars.contains { (0x4E00...0x9FFF).contains($0.value) }
}

func isLatinSurface(_ value: String) -> Bool {
  guard let first = value.unicodeScalars.first else { return false }
  return CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'")
    .contains(first)
}

extension LyricsTimeline.Cue {
  /// 整句文本：全拉丁 token 时空格拼接，否则用原文（paint.js cueLine）
  var lineText: String {
    let text = text ?? ""
    let tokens = tokens ?? []
    if text.contains(where: { $0.isWhitespace }) || tokens.isEmpty { return text }
    if tokens.allSatisfy({ isLatinSurface($0.display) }) {
      return tokens.map(\.display).joined(separator: " ")
    }
    return text
  }

  /// 整句罗马音：逐 token romaji 拼接，缺了退回 cue.romaji（paint.js cueRomaji）
  var lineRomaji: String {
    let bits = (tokens ?? [])
      .map { $0.romajiText.trimmingCharacters(in: .whitespaces) }
      .filter { !$0.isEmpty }
    if !bits.isEmpty { return bits.joined(separator: " ") }
    return (romaji ?? "").trimmingCharacters(in: .whitespaces)
  }

  /// 假名碎 token 合并到前一个有注音的词上（paint.js clusterTokens），
  /// 让罗马音/词义落在整段唱词下面。
  var clusteredTokens: [LyricsTimeline.Token] {
    var out: [LyricsTimeline.Token] = []
    for tok in tokens ?? [] {
      var cur = tok
      cur.text = tok.text ?? ""
      if var prev = out.last,
         isKanaText(prev.text ?? ""),
         isKanaText(cur.text ?? ""),
         prev.hasAnno, !cur.hasAnno {
        prev.text = (prev.text ?? "") + (cur.text ?? "")
        prev.surface = (prev.surface ?? "") + (cur.surface ?? "")
        prev.end_ms = cur.end_ms
        out[out.count - 1] = prev
        continue
      }
      out.append(cur)
    }
    return out
  }
}
