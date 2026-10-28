import AVFoundation
import SwiftUI
import VisionKit

/// 扫码：包装 DataScannerViewController，识别到二维码返回 payload 并自动关闭。
struct QRScannerSheet: UIViewControllerRepresentable {
  var onResult: (String) -> Void
  var onDismiss: () -> Void

  func makeCoordinator() -> Coordinator { Coordinator(self) }

  func makeUIViewController(context: Context) -> UINavigationController {
    let scanner = DataScannerViewController(
      recognizedDataTypes: [.barcode(symbologies: [.qr])],
      qualityLevel: .balanced,
      recognizesMultipleItems: false,
      isGuidanceEnabled: true,
      isHighlightingEnabled: true)
    scanner.delegate = context.coordinator
    scanner.navigationItem.leftBarButtonItem = UIBarButtonItem(
      barButtonSystemItem: .cancel,
      target: context.coordinator,
      action: #selector(Coordinator.cancel))
    let nav = UINavigationController(rootViewController: scanner)
    nav.isModalInPresentation = true
    DispatchQueue.main.async { try? scanner.startScanning() }
    return nav
  }

  func updateUIViewController(_ uiViewController: UINavigationController, context: Context) {}

  static var isAvailable: Bool {
    DataScannerViewController.isSupported && DataScannerViewController.isAvailable
  }

  final class Coordinator: NSObject, DataScannerViewControllerDelegate {
    let parent: QRScannerSheet
    private var didResolve = false
    init(_ parent: QRScannerSheet) { self.parent = parent }

    @objc func cancel() { parent.onDismiss() }

    func dataScanner(_ dataScanner: DataScannerViewController,
                     didAdd addedItems: [RecognizedItem],
                     allItems: [RecognizedItem]) {
      guard !didResolve else { return }
      for item in addedItems {
        if case .barcode(let barcode) = item, let value = barcode.payloadStringValue {
          didResolve = true
          dataScanner.stopScanning()
          parent.onResult(value)
          return
        }
      }
    }
  }
}
