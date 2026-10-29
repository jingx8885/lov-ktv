import Foundation

/// 词卡（_card_view）：全局单词本里的一条
struct ReciteCard: Decodable, Sendable, Identifiable {
  var id: String { card_id }
  var card_id: String
  var song_id: String?
  var song_title: String?
  var text: String?
  var zh: String?
  var romaji: String?
  var line_text: String?
  var start_ms: Int?
  var end_ms: Int?
  var stage: Int?
  var reps: Int?
  var due_at: Int?
  var retired: Bool?
  var skipped: Bool?
}

/// /api/learn/deck 的汇总
struct ReciteDeck: Decodable, Sendable {
  var deck: String
  var total: Int
  var due: Int
  var new: Int
  var learning: Int
  var mastered: Int
  var skipped: Int
  var streak: Int
  var today: Int
  var sizes: [Int]
  var cards: [ReciteCard]?
}

/// /api/learn/session 的一轮
struct ReciteSession: Decodable, Sendable {
  var deck: String
  var cards: [ReciteItem]
  var total: Int
}

struct ReciteItem: Decodable, Sendable, Identifiable {
  var id: String
  var kind: String        // meaning | reverse | blank | listen | match | word | sentence
  var prompt: String?
  var stem: String?
  var choices: [Choice]?
  var pairs: [MatchPair]?
  var answer: Int?
  var answer_text: String?
  var card_id: String?
  var stage: Int?
  var audio: Bool?
  var blank: Blank?
  var detail: Detail?

  struct Choice: Decodable, Sendable, Identifiable {
    var id: Int
    var text: String
  }
  struct MatchPair: Decodable, Sendable, Identifiable {
    var id: Int
    var left: String
    var right: String
    var key: String?
  }
  struct Blank: Decodable, Sendable {
    var before: String?
    var after: String?
  }
  struct Detail: Decodable, Sendable {
    var text: String?
    var zh: String?
    var romaji: String?
    var line_text: String?
    var start_ms: Int?
    var end_ms: Int?
    var song_id: String?
  }
}

/// /api/songs/{id}/learn/words 的筛选负载
struct SongWordsPack: Decodable, Sendable {
  var song_id: String
  var title: String?
  var language: String?
  var first_setup: Bool
  var total: Int?
  var due: Int?
  var words: [SongWord]
}

struct SongWord: Decodable, Sendable, Identifiable {
  var id: String { word_id }
  var word_id: String
  var language: String?
  var text: String?
  var zh: String?
  var romaji: String?
  var line_text: String?
  var start_ms: Int?
  var end_ms: Int?
  var skipped: Bool?
  var retired: Bool?
}
