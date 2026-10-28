import Foundation

/// 学习 campaign：一首歌的单元×技能进度总览
struct LearnCampaign: Decodable, Sendable {
  var song_id: String
  var title: String?
  var language: String?
  var goal: Goal
  var mistakes: Int
  var units: [Unit]
  var pass_pct: Int

  struct Goal: Decodable, Sendable {
    var words: DoneTotal
    var sentences: DoneTotal
    var read: DoneTotal
    var cleared: Bool
  }
  struct DoneTotal: Decodable, Sendable {
    var done: Int
    var total: Int
  }
  struct Unit: Decodable, Sendable, Identifiable {
    var id: String
    var index: Int
    var preview: String?
    var skills: [Skill]
  }
  struct Skill: Decodable, Sendable, Identifiable {
    var id: String        // word | sentence | listen | read
    var status: String    // locked | ready | passed | mastered
    var score: Int
    var attempts: Int
    var play_mode: String?
    var locked: Bool { status == "locked" }
    var label: String {
      switch id {
      case "word": return "单词"
      case "sentence": return "句子"
      case "listen": return "听力"
      case "read": return "跟读"
      default: return id
      }
    }
  }
}

/// 一节课：题目列表（多选/配对）或 read 技能的 play_mode
struct Lesson: Decodable, Sendable {
  var unit_id: String
  var skill: String
  var play_mode: String?
  var lines: [LessonLine]
  var items: [LessonItem]
  var total: Int
  var pass_pct: Int
  var title: String?

  struct LessonLine: Decodable, Sendable {
    var index: Int
    var text: String?
    var zh: String?
    var romaji: String?
    var start_ms: Int?
    var end_ms: Int?
    var words: [LessonWord]?
  }

  struct LessonWord: Decodable, Sendable, Identifiable {
    var id: Int { start_ms ?? 0 }
    var text: String?
    var romaji: String?
    var translation: String?
    var zh: String?
    var start_ms: Int?
    var end_ms: Int?
  }

  struct LessonItem: Decodable, Sendable, Identifiable {
    var id: String
    var kind: String      // word | meaning | blank | listen | reverse | match | sentence
    var prompt: String?
    var stem: String?
    var choices: [Choice]?
    var pairs: [MatchPair]?
    var answer_text: String?
    var romaji: String?
    var translation: String?
  }

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
}

/// 提交课后服务端回包（宽松解码，字段按 apply_lesson_result + campaign）
struct LessonResult: Decodable, Sendable {
  var pct: Int?
  var passed: Bool?
  var score: Int?
  var mistakes: Int?
  var pass_pct: Int?
}
