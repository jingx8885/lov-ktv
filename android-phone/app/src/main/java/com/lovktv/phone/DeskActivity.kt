package com.lovktv.phone

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.view.KeyEvent
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.PermissionRequest
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient

class DeskActivity : Activity() {
    private lateinit var webView: WebView
    private var roomCode = ""
    private var server = ""
    private var lanOrigin = ""
    private var micHost = ""
    private var micPort = 0
    private var micRate = LanMic.SAMPLE_RATE
    private var fileCallback: ValueCallback<Array<Uri>>? = null
    private var pendingWebPerm: PermissionRequest? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_desk)
        server = intent.getStringExtra(EXTRA_SERVER).orEmpty().ifBlank { Prefs.serverUrl(this) }
        roomCode = intent.getStringExtra(EXTRA_ROOM).orEmpty().ifBlank { Prefs.roomCode(this) }
        lanOrigin = intent.getStringExtra(EXTRA_LAN).orEmpty().ifBlank { Prefs.lanUrl(this) }
        micHost = intent.getStringExtra(EXTRA_MIC_HOST).orEmpty()
        micPort = intent.getIntExtra(EXTRA_MIC_PORT, 0)
        micRate = intent.getIntExtra(EXTRA_MIC_RATE, LanMic.SAMPLE_RATE).takeIf { it > 0 } ?: LanMic.SAMPLE_RATE
        webView = findViewById(R.id.webview)
        bindWebView()
        loadDesk()
    }

    private fun bindWebView() {
        webView.setBackgroundColor(Color.parseColor("#0B1020"))
        runCatching {
            val cookies = CookieManager.getInstance()
            cookies.setAcceptCookie(true)
            cookies.setAcceptThirdPartyCookies(webView, true)
        }
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = false
            mediaPlaybackRequiresUserGesture = false
            mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            cacheMode = WebSettings.LOAD_DEFAULT
            useWideViewPort = true
            loadWithOverviewMode = true
            builtInZoomControls = false
            displayZoomControls = false
            userAgentString = "$userAgentString LovKtvAndroidPhone/1.0"
        }
        webView.addJavascriptInterface(NativeBridge(), "LovKtvNative")
        webView.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest) {
                runOnUiThread { handleWebPermission(request) }
            }

            override fun onPermissionRequestCanceled(request: PermissionRequest) {
                if (pendingWebPerm === request) pendingWebPerm = null
            }

            override fun onShowFileChooser(
                view: WebView?,
                callback: ValueCallback<Array<Uri>>?,
                params: FileChooserParams?,
            ): Boolean {
                fileCallback?.onReceiveValue(null)
                fileCallback = callback
                val intent = params?.createIntent() ?: Intent(Intent.ACTION_GET_CONTENT).setType("*/*")
                return try {
                    startActivityForResult(intent, REQ_FILE)
                    true
                } catch (_: Exception) {
                    fileCallback = null
                    false
                }
            }
        }
        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val url = request.url ?: return false
                val host = url.host.orEmpty()
                if (host.contains("weixin") || host.contains("wechat")) return false
                if (url.scheme == "http" || url.scheme == "https") {
                    view.loadUrl(url.toString())
                    return true
                }
                return false
            }

            override fun onReceivedError(
                view: WebView,
                request: WebResourceRequest,
                error: android.webkit.WebResourceError,
            ) {
                if (!request.isForMainFrame) return
                val failed = request.url?.toString().orEmpty()
                if (lanOrigin.isNotBlank() && failed.startsWith(lanOrigin)) {
                    view.loadUrl(DeskPage.url(server, roomCode, ""))
                }
            }
        }
    }

    private fun loadDesk() {
        webView.loadUrl(DeskPage.url(server, roomCode, lanOrigin))
    }

    private fun hasLanMic(): Boolean = NativeMic.canStart(micHost, micPort)

    private fun handleWebPermission(request: PermissionRequest) {
        pendingWebPerm = request
        if (hasAudio(this)) {
            grantWebPermission(request)
            return
        }
        requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQ_WEB_MIC)
    }

    private fun grantWebPermission(request: PermissionRequest) {
        request.grant(request.resources)
        if (pendingWebPerm === request) pendingWebPerm = null
    }

    private fun denyWebPermission(request: PermissionRequest?) {
        request?.deny()
        if (pendingWebPerm === request) pendingWebPerm = null
    }

    private fun startNativeMic() {
        if (!hasLanMic()) {
            notifyJs(false, getString(R.string.mic_need_tv))
            return
        }
        if (!hasAudio(this)) {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQ_NATIVE_MIC)
            return
        }
        MicService.start(this, micHost, micPort, micRate)
        notifyJs(true, "")
    }

    private fun notifyJs(ok: Boolean, err: String) {
        if (!::webView.isInitialized) return
        val safe = err.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")
        webView.evaluateJavascript(
            "window.LovKtvOnMic && window.LovKtvOnMic(${if (ok) "true" else "false"}, '$safe')",
            null,
        )
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        val granted = grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED
        when (requestCode) {
            REQ_WEB_MIC -> {
                val req = pendingWebPerm
                if (granted && req != null) grantWebPermission(req)
                else denyWebPermission(req)
            }
            REQ_NATIVE_MIC -> {
                if (granted) {
                    MicService.start(this, micHost, micPort, micRate)
                    notifyJs(true, "")
                } else {
                    notifyJs(false, getString(R.string.mic_denied))
                }
            }
        }
    }

    override fun onDestroy() {
        pendingWebPerm?.deny()
        pendingWebPerm = null
        fileCallback?.onReceiveValue(null)
        fileCallback = null
        MicService.stop(this)
        webView.destroy()
        super.onDestroy()
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQ_FILE) return
        val uris = if (resultCode == RESULT_OK) WebChromeClient.FileChooserParams.parseResult(resultCode, data) else null
        fileCallback?.onReceiveValue(uris)
        fileCallback = null
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (keyCode == KeyEvent.KEYCODE_BACK && webView.canGoBack()) {
            webView.goBack()
            return true
        }
        return super.onKeyDown(keyCode, event)
    }

    inner class NativeBridge {
        @JavascriptInterface
        fun hasLanMic(): Boolean = this@DeskActivity.hasLanMic()

        @JavascriptInterface
        fun isMicLive(): Boolean = MicService.running

        @JavascriptInterface
        fun startMic() {
            runOnUiThread { startNativeMic() }
        }

        @JavascriptInterface
        fun stopMic() {
            runOnUiThread { MicService.stop(this@DeskActivity) }
        }
    }

    companion object {
        const val EXTRA_SERVER = "server"
        const val EXTRA_ROOM = "room"
        const val EXTRA_LAN = "lan"
        const val EXTRA_MIC_HOST = "mic_host"
        const val EXTRA_MIC_PORT = "mic_port"
        const val EXTRA_MIC_RATE = "mic_rate"
        private const val REQ_FILE = 22
        private const val REQ_WEB_MIC = 23
        private const val REQ_NATIVE_MIC = 24

        fun hasAudio(activity: Activity): Boolean {
            return activity.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
        }
    }
}
