import XCTest
@testable import LovKTV

final class ConnectionValidatorTests: XCTestCase {
  func testAcceptsHTTPSAndRoom() throws {
    let c = try ConnectionValidator.parse("https://example.com", room: "k7q2")
    XCTAssertEqual(c.server.absoluteString, "https://example.com/")
    XCTAssertEqual(c.room, "K7Q2")
    XCTAssertEqual(c.mode, .selfHosted)
  }

  func testAcceptsLANHttp() throws {
    for host in ["http://192.168.1.8:8790", "http://10.0.0.2", "http://172.16.0.5", "http://ktv.local"] {
      XCTAssertNoThrow(try ConnectionValidator.parse(host, room: "ABCD"))
    }
  }

  func testRejectsNonLocalHTTP() {
    XCTAssertThrowsError(try ConnectionValidator.parse("http://8.8.8.8", room: "ABCD")) { error in
      XCTAssertEqual(error as? ConnectionError, .insecureURL)
    }
  }

  func testRejectsBadRoom() {
    XCTAssertThrowsError(try ConnectionValidator.parse("https://a.com", room: "abc"))
    XCTAssertThrowsError(try ConnectionValidator.parse("https://a.com", room: "TOOLONGROOMCODE123"))
  }

  func testScannedQRWithRoomParam() throws {
    let c = try ConnectionValidator.parse("https://ktv.lovbrowser.com?room=zz99")
    XCTAssertEqual(c.mode, .official)
    XCTAssertEqual(c.room, "ZZ99")
  }

  func testRejectsNonRoomQuery() {
    XCTAssertThrowsError(try ConnectionValidator.parse("https://a.com?x=1", room: "ABCD")) { error in
      XCTAssertEqual(error as? ConnectionError, .unexpectedQuery)
    }
  }
}

final class RemotePathTests: XCTestCase {
  func testSelfHostedPassthrough() {
    XCTAssertEqual(RemotePath.map("/api/rooms/ABCD", official: false), "/api/rooms/ABCD")
    XCTAssertEqual(RemotePath.map("/api/remote/reports", official: false), "/api/remote/reports")
  }

  func testOfficialRewrite() {
    XCTAssertEqual(RemotePath.map("/api/rooms/ABCD", official: true), "/api/remote/ios/rooms/ABCD")
    XCTAssertEqual(RemotePath.map("/api/songs?q=x", official: true), "/api/remote/ios/songs?q=x")
    XCTAssertEqual(RemotePath.map("/api/remote/reports", official: true), "/api/remote/ios/reports")
  }
}

final class APIWhitelistTests: XCTestCase {
  func testGETPaths() {
    XCTAssertTrue(APIWhitelist.allows(path: "/api/songs?q=abc&page=1", method: "GET"))
    XCTAssertTrue(APIWhitelist.allows(path: "/api/rooms/K7Q2", method: "GET"))
    XCTAssertFalse(APIWhitelist.allows(path: "/api/admin/users", method: "GET"))
    XCTAssertFalse(APIWhitelist.allows(path: "/api/songs", method: "GET")) // 必须带 query
    XCTAssertFalse(APIWhitelist.allows(path: "/media/x/original.mp3", method: "GET"))
  }

  func testPOSTPaths() {
    for cmd in ["queue", "play", "skip", "mix", "bump"] {
      XCTAssertTrue(APIWhitelist.allows(path: "/api/rooms/K7Q2/\(cmd)", method: "POST"), cmd)
    }
    XCTAssertTrue(APIWhitelist.allows(path: "/api/remote/reports", method: "POST"))
    XCTAssertFalse(APIWhitelist.allows(path: "/api/rooms/K7Q2/remove", method: "POST"))
    XCTAssertFalse(APIWhitelist.allows(path: "/api/rooms/K7Q2", method: "POST"))
    XCTAssertFalse(APIWhitelist.allows(path: "/api/rooms/k7q2/skip", method: "POST")) // 小写房间码不允许
  }
}

final class SongDecodingTests: XCTestCase {
  func testDecodesSnakeCase() throws {
    let json = """
    {"songs":[{"id":"a1","song_id":"a1","title":"晴天","artist":"周杰伦","status":"ready"}],"total":1}
    """.data(using: .utf8)!
    let page = try JSONDecoder().decode(SongsPage.self, from: json)
    XCTAssertEqual(page.total, 1)
    XCTAssertEqual(page.songs[0].songID, "a1")
    XCTAssertEqual(page.songs[0].displayTitle, "晴天")
    XCTAssertTrue(page.songs[0].isReady)
  }

  func testRoomSnapshot() throws {
    let json = """
    {"code":"K7Q2","paused":true,"volume":55,
     "now_playing":{"song_id":"n1","title":"海阔天空","artist":"Beyond"},
     "queue":[{"song_id":"q1","title":"红豆"},{"song_id":"q2","title":"童话"}]}
    """.data(using: .utf8)!
    let snap = try JSONDecoder().decode(RoomSnapshot.self, from: json)
    XCTAssertTrue(snap.paused)
    XCTAssertEqual(snap.volume, 55)
    XCTAssertEqual(snap.now_playing?.displayTitle, "海阔天空")
    XCTAssertEqual(snap.queueCount, 2)
  }

  func testKeychainKeyFormat() {
    XCTAssertTrue(KeychainStore.isValidKey("lkr_" + String(repeating: "a", count: 43)))
    XCTAssertFalse(KeychainStore.isValidKey("lkr_short"))
    XCTAssertFalse(KeychainStore.isValidKey("abc_" + String(repeating: "a", count: 43)))
  }
}
