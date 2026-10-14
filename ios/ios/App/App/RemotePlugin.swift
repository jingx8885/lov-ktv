import Capacitor
import AVFoundation
import VisionKit
import MediaPlayer
import WebKit
import Security

@objc(RemotePlugin)
public class RemotePlugin: CAPPlugin, CAPBridgedPlugin, URLSessionTaskDelegate, DataScannerViewControllerDelegate, AVAudioPlayerDelegate {
    public let identifier = "RemotePlugin"
    public let jsName = "Remote"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "configure", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "request", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "scan", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "listen", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "stop", returnType: CAPPluginReturnPromise)
    ]
    public override func shouldOverrideLoad(_ navigationAction: WKNavigationAction) -> NSNumber? {
        guard let url = navigationAction.request.url else { return true }
        return NSNumber(value: !(url.scheme == "capacitor" && url.host == "localhost"))
    }
    public override func load() {
        NotificationCenter.default.addObserver(self, selector: #selector(audioInterrupted(_:)),
            name: AVAudioSession.interruptionNotification, object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(audioRouteChanged(_:)),
            name: AVAudioSession.routeChangeNotification, object: nil)
    }
    @objc private func audioInterrupted(_ notification: Notification) {
        player?.pause()
    }
    @objc private func audioRouteChanged(_ notification: Notification) {
        if let reason = notification.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt,
           reason == AVAudioSession.RouteChangeReason.oldDeviceUnavailable.rawValue { player?.pause() }
    }
    public func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) { stopAudio() }
    private var origin: URL?
    private var official = false
    private var apiKey = ""
    private let officialOrigin = "https://ktv.lovbrowser.com"
    private var keyQuery: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: "com.lovktv.phone.official",
         kSecAttrAccount as String: "remote-api-key"]
    }
    private func savedKey() throws -> String {
        var query = keyQuery
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecItemNotFound { return "" }
        guard status == errSecSuccess, let data = result as? Data,
              let key = String(data: data, encoding: .utf8) else {
            throw NSError(domain: "RemoteKeychain", code: Int(status))
        }
        return key
    }
    private func saveKey(_ key: String) throws {
        var attributes: [String: Any] = [kSecValueData as String: Data(key.utf8),
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly]
        let status = SecItemUpdate(keyQuery as CFDictionary, attributes as CFDictionary)
        if status == errSecItemNotFound {
            attributes.merge(keyQuery) { _, new in new }
            let added = SecItemAdd(attributes as CFDictionary, nil)
            guard added == errSecSuccess else { throw NSError(domain: "RemoteKeychain", code: Int(added)) }
        } else if status != errSecSuccess { throw NSError(domain: "RemoteKeychain", code: Int(status)) }
    }
    private func clearKey() throws {
        let status = SecItemDelete(keyQuery as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw NSError(domain: "RemoteKeychain", code: Int(status))
        }
    }
    private func authorize(_ request: inout URLRequest) {
        request.setValue("ios", forHTTPHeaderField: "X-LovKTV-Platform")
        if official { request.setValue("Bearer " + apiKey, forHTTPHeaderField: "Authorization") }
    }
    private func remotePath(_ path: String) -> String {
        guard official else { return path }
        return path == "/api/remote/reports" ? "/api/remote/ios/reports"
            : "/api/remote/ios" + String(path.dropFirst(4))
    }
    private var scanCall: CAPPluginCall?
    private var player: AVAudioPlayer?
    private var audioGeneration = 0
    private lazy var session: URLSession = {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 20
        config.timeoutIntervalForResource = 60
        config.httpCookieAcceptPolicy = .never
        config.httpShouldSetCookies = false
        return URLSession(configuration: config, delegate: self, delegateQueue: .main)
    }()

    @objc func configure(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            self.session.invalidateAndCancel()
            let configuration = URLSessionConfiguration.ephemeral
            configuration.timeoutIntervalForRequest = 20
            configuration.timeoutIntervalForResource = 60
            configuration.httpCookieAcceptPolicy = .never
            configuration.httpShouldSetCookies = false
            self.session = URLSession(configuration: configuration, delegate: self, delegateQueue: .main)
            self.stopAudio()
            self.origin = nil
            self.apiKey = ""
            self.official = false
            let raw = call.getString("server") ?? ""
            if raw.isEmpty {
                do { try self.clearKey(); call.resolve() }
                catch { call.reject("无法清除安全存储，请重试") }
                return
            }
            guard let url = URL(string: raw), let host = url.host?.lowercased(),
                  url.user == nil, url.password == nil, url.query == nil, url.fragment == nil,
                  url.path.isEmpty || url.path == "/",
                  url.scheme == "https" || (url.scheme == "http" && Self.local(host)) else {
                call.reject("请使用 HTTPS 或局域网 HTTP 根地址"); return
            }
            let official = (call.getBool("official") ?? false) || host == "ktv.lovbrowser.com"
            if official {
                guard raw == self.officialOrigin else { call.reject("官方服务地址无效"); return }
                do {
                    let supplied = call.getString("apiKey") ?? ""
                    let key = supplied.isEmpty ? try self.savedKey() : supplied
                    guard key.range(of: #"^lkr_[A-Za-z0-9_-]{43}$"#, options: .regularExpression) != nil else {
                        call.reject("API key 无效或已失效"); return
                    }
                    if !supplied.isEmpty { try self.saveKey(key) }
                    self.apiKey = key
                } catch { call.reject("无法读取或保存安全存储，请重试"); return }
            }
            self.official = official
            self.origin = url
            call.resolve()
        }
    }
    private static func local(_ host: String) -> Bool {
        if host.hasSuffix(".local") { return true }
        let parts = host.split(separator: ".").compactMap { Int($0) }
        return parts.count == 4 && parts.allSatisfy { (0...255).contains($0) } &&
            (parts[0] == 10 || (parts[0] == 192 && parts[1] == 168) ||
             (parts[0] == 172 && (16...31).contains(parts[1])))
    }
    private func allowed(_ path: String, _ method: String) -> Bool {
        let pattern = method == "GET"
            ? #"^/api/(songs\?[^#]*|rooms/[A-Z0-9]{4,12})$"#
            : #"^/api/(rooms/[A-Z0-9]{4,12}/(queue|play|skip|mix)|remote/reports)$"#
        return ["GET", "POST"].contains(method) && path.range(of: pattern, options: .regularExpression) != nil
    }
    @objc func request(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            guard let origin = self.origin, let path = call.getString("path"),
                  let method = call.getString("method"), self.allowed(path, method),
                  let url = URL(string: origin.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + self.remotePath(path)),
                  url.host == origin.host else { call.reject("请求不在遥控接口白名单内"); return }
            var request = URLRequest(url: url)
            self.authorize(&request)
            request.httpMethod = method
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            if method == "POST" { request.httpBody = (call.getString("body") ?? "{}").data(using: .utf8) }
            self.session.dataTask(with: request) { data, response, error in
                guard error == nil, let data = data, data.count <= 4_000_000,
                      let http = response as? HTTPURLResponse,
                      let body = String(data: data, encoding: .utf8) else {
                    call.reject("无法连接服务器，请检查地址、网络及局域网权限"); return
                }
                call.resolve(["status": http.statusCode, "body": body])
            }.resume()
        }
    }
    // Redirects must not turn a configured server into an external content source.
    public func urlSession(_ session: URLSession, task: URLSessionTask,
                           willPerformHTTPRedirection response: HTTPURLResponse,
                           newRequest request: URLRequest,
                           completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
    @objc func scan(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            guard self.scanCall == nil else { call.reject("扫码正在进行"); return }
            self.scanCall = call
            AVCaptureDevice.requestAccess(for: .video) { granted in
                DispatchQueue.main.async {
                    guard granted else { self.finishScan(nil, "请在系统设置中允许相机，或手动填写地址"); return }
                    guard DataScannerViewController.isSupported, DataScannerViewController.isAvailable else {
                        self.finishScan(nil, "此设备不支持扫码，请手动填写地址"); return
                    }
                    let scanner = DataScannerViewController(recognizedDataTypes: [.barcode(symbologies: [.qr])],
                        qualityLevel: .balanced, recognizesMultipleItems: false, isGuidanceEnabled: true,
                        isHighlightingEnabled: true)
                    scanner.delegate = self
                    scanner.navigationItem.leftBarButtonItem = UIBarButtonItem(barButtonSystemItem: .cancel,
                        target: self, action: #selector(self.cancelScan))
                    let navigation = UINavigationController(rootViewController: scanner)
                    navigation.isModalInPresentation = true
                    self.bridge?.viewController?.present(navigation, animated: true) {
                        do { try scanner.startScanning() }
                        catch { self.finishScan(nil, "相机不可用，请手动填写地址") }
                    }
                }
            }
        }
    }
    @objc private func cancelScan() { finishScan(nil, "已取消扫码") }
    public func dataScanner(_ dataScanner: DataScannerViewController, didAdd addedItems: [RecognizedItem], allItems: [RecognizedItem]) {
        for item in addedItems {
            if case .barcode(let barcode) = item, let value = barcode.payloadStringValue {
                dataScanner.stopScanning(); finishScan(value, nil); return
            }
        }
    }
    public func dataScanner(_ dataScanner: DataScannerViewController, becameUnavailableWithError error: DataScannerViewController.ScanningUnavailable) {
        finishScan(nil, "相机不可用，请重试或手动填写地址")
    }
    private func finishScan(_ value: String?, _ error: String?) {
        bridge?.viewController?.dismiss(animated: true)
        if let value = value { scanCall?.resolve(["value": value]) }
        else { scanCall?.reject(error ?? "扫码失败") }
        scanCall = nil
    }
    @objc func listen(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            guard let origin = self.origin, let id = call.getString("id"),
                  id.range(of: #"^[A-Za-z0-9_-]{1,100}$"#, options: .regularExpression) != nil,
                  let url = URL(string: origin.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + (self.official ? "/api/remote/ios/media/" + id : "/media/" + id + "/original.mp3")) else {
                call.reject("请先连接服务器"); return
            }
            self.stopAudio()
            let generation = self.audioGeneration
            var request = URLRequest(url: url)
            self.authorize(&request)
            self.session.downloadTask(with: request) { file, response, error in
                guard generation == self.audioGeneration else { call.reject("试听已取消"); return }
                if self.official, let status = (response as? HTTPURLResponse)?.statusCode, [401, 403].contains(status) {
                    call.reject("API key 无效或已失效"); return
                }
                guard error == nil, (response as? HTTPURLResponse)?.statusCode == 200,
                      let file = file,
                      let size = try? file.resourceValues(forKeys: [.fileSizeKey]).fileSize,
                      size <= 30_000_000 else { call.reject("无法试听：需服务器本地音频（最大 30 MB），不支持外部重定向"); return }
                do {
                    let data = try Data(contentsOf: file)
                    try AVAudioSession.sharedInstance().setCategory(.playback, mode: .default)
                    try AVAudioSession.sharedInstance().setActive(true)
                    self.player = try AVAudioPlayer(data: data)
                    self.player?.delegate = self
                    self.player?.play()
                    MPNowPlayingInfoCenter.default().nowPlayingInfo = [MPMediaItemPropertyTitle: "LovKTV 服务器试听"]
                    MPRemoteCommandCenter.shared().pauseCommand.removeTarget(nil)
                    MPRemoteCommandCenter.shared().playCommand.removeTarget(nil)
                    MPRemoteCommandCenter.shared().pauseCommand.addTarget { [weak self] _ in self?.player?.pause(); return .success }
                    MPRemoteCommandCenter.shared().playCommand.addTarget { [weak self] _ in self?.player?.play(); return .success }
                    call.resolve()
                } catch { self.stopAudio(); call.reject("音频无法播放") }
            }.resume()
        }
    }
    private func stopAudio() {
        audioGeneration += 1
        player?.stop(); player = nil
        MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
        MPRemoteCommandCenter.shared().pauseCommand.removeTarget(nil)
        MPRemoteCommandCenter.shared().playCommand.removeTarget(nil)
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }
    @objc func stop(_ call: CAPPluginCall) {
        DispatchQueue.main.async { self.stopAudio(); call.resolve() }
    }
}
