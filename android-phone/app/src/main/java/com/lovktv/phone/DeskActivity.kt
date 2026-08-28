package com.lovktv.phone

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.view.KeyEvent
import android.webkit.CookieManager
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
    private var fileCallback: ValueCallback<Array<Uri>>? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_desk)
        server = intent.getStringExtra(EXTRA_SERVER).orEmpty().ifBlank { Prefs.serverUrl(this) }
        roomCode = intent.getStringExtra(EXTRA_ROOM).orEmpty().ifBlank { Prefs.roomCode(this) }
        lanOrigin = intent.getStringExtra(EXTRA_LAN).orEmpty().ifBlank { Prefs.lanUrl(this) }
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
        webView.webChromeClient = object : WebChromeClient() {
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

    override fun onDestroy() {
        fileCallback?.onReceiveValue(null)
        fileCallback = null
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

    companion object {
        const val EXTRA_SERVER = "server"
        const val EXTRA_ROOM = "room"
        const val EXTRA_LAN = "lan"
        const val EXTRA_MIC_HOST = "mic_host"
        const val EXTRA_MIC_PORT = "mic_port"
        const val EXTRA_MIC_RATE = "mic_rate"
        private const val REQ_FILE = 22
    }
}
