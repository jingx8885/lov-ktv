package com.lovktv.tv

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.BitmapFactory
import android.graphics.Color
import android.os.Bundle
import android.view.KeyEvent
import android.view.View
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.app.Activity
import android.view.SurfaceView
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast
import java.net.URL
import java.util.concurrent.Executors

class TvActivity : Activity(), TvHost {
    private lateinit var webView: WebView
    private lateinit var coverView: ImageView
    private lateinit var lyricsView: TextView
    private lateinit var silentMtv: SilentMtv

    private val io = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "lovktv-cover").apply { isDaemon = true }
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_tv)
        webView = findViewById(R.id.webview)
        coverView = findViewById(R.id.mtvCover)
        lyricsView = findViewById(R.id.nativeLyrics)
        silentMtv = SilentMtv(findViewById<SurfaceView>(R.id.mtvNative))

        runCatching {
            val cookies = CookieManager.getInstance()
            cookies.setAcceptCookie(true)
            cookies.setAcceptThirdPartyCookies(webView, true)
        }

        webView.setBackgroundColor(Color.TRANSPARENT)
        webView.setLayerType(View.LAYER_TYPE_HARDWARE, null)
        webView.isFocusable = true
        webView.isFocusableInTouchMode = true
        webView.addJavascriptInterface(TvBridge(this), "LovKtvNative")
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = false
            mediaPlaybackRequiresUserGesture = false
            mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            cacheMode = WebSettings.LOAD_NO_CACHE
            userAgentString = "$userAgentString LovKtvAndroidTV/1.0"
        }
        webView.webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(consoleMessage: android.webkit.ConsoleMessage?): Boolean {
                val msg = consoleMessage ?: return true
                android.util.Log.e("lovktv-web", "${msg.message()} @${msg.sourceId()}:${msg.lineNumber()}")
                return true
            }
        }
        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                return false
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                view?.evaluateJavascript(
                    "(function(){document.documentElement.style.background='transparent';" +
                        "document.body.style.background='transparent';" +
                        "var s=document.getElementById('start');if(s)s.click();})()",
                    null,
                )
            }

            override fun onReceivedError(
                view: WebView,
                request: WebResourceRequest,
                error: WebResourceError,
            ) {
                if (request.isForMainFrame) {
                    Toast.makeText(this@TvActivity, getString(R.string.server_error), Toast.LENGTH_LONG).show()
                }
            }
        }
        HostService.ensureStarted(this)
        loadWhenReady()
        webView.requestFocus()
    }

    override fun runOnUi(block: () -> Unit) {
        runOnUiThread(block)
    }

    override fun playMtv(url: String) {
        silentMtv.play(url)
        if (silentMtv.url.isNotBlank()) coverView.visibility = View.GONE
    }

    override fun stopMtv() {
        silentMtv.stop()
        coverView.visibility = View.GONE
        coverView.setImageDrawable(null)
    }

    override fun pauseMtv() {
        silentMtv.pause()
    }

    override fun resumeMtv() {
        silentMtv.resume()
    }

    override fun seekMtv(ms: Int) {
        silentMtv.seek(ms)
    }

    override fun mtvPositionMs(): Int = silentMtv.positionMs()

    override fun mtvDurationMs(): Int = silentMtv.durationMs()

    override fun mtvPlaying(): Boolean = silentMtv.isPlaying()

    override fun showCover(url: String) {
        val next = url.trim()
        if (next.isBlank()) {
            coverView.visibility = View.GONE
            coverView.setImageDrawable(null)
            return
        }
        io.execute {
            val bmp = runCatching {
                URL(next).openStream().use { BitmapFactory.decodeStream(it) }
            }.getOrNull()
            runOnUiThread {
                if (bmp == null) return@runOnUiThread
                coverView.setImageBitmap(bmp)
                if (!silentMtv.isPlaying()) coverView.visibility = View.VISIBLE
            }
        }
    }

    override fun showLyrics(cur: String, zh: String, next: String) {
        lyricsView.text = ""
        lyricsView.visibility = View.GONE
    }

    private fun loadWhenReady() {
        webView.post(object : Runnable {
            private var tries = 0

            override fun run() {
                if (HostRuntime.ready && HostRuntime.port in 1..65535) {
                    val port = HostRuntime.port
                    webView.loadUrl("http://127.0.0.1:$port/tv.html?androidtv=1")
                    return
                }
                tries += 1
                if (tries < 80) {
                    webView.postDelayed(this, 100)
                } else {
                    Toast.makeText(this@TvActivity, getString(R.string.server_error), Toast.LENGTH_LONG).show()
                }
            }
        })
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (keyCode == KeyEvent.KEYCODE_BACK && webView.canGoBack()) {
            webView.goBack()
            return true
        }
        if (keyCode == KeyEvent.KEYCODE_MENU || keyCode == KeyEvent.KEYCODE_INFO) {
            startActivity(
                Intent(this, SetupActivity::class.java).putExtra(SetupActivity.EXTRA_FORCE, true),
            )
            finish()
            return true
        }
        if (event != null && RemoteKeys.interceptInNative(keyCode)) {
            sendRemote(RemoteKeys.jsAction(keyCode) ?: return super.onKeyDown(keyCode, event))
            return true
        }
        return super.onKeyDown(keyCode, event)
    }

    private fun sendRemote(action: String) {
        val safe = action.replace(Regex("[^A-Za-z]"), "")
        if (safe.isEmpty()) return
        webView.evaluateJavascript(
            "window.LovKtvRemote&&window.LovKtvRemote.$safe&&window.LovKtvRemote.$safe()",
            null,
        )
    }

    override fun onPause() {
        pauseMtv()
        webView.onPause()
        super.onPause()
    }

    override fun onResume() {
        super.onResume()
        webView.onResume()
        webView.requestFocus()
        resumeMtv()
    }

    override fun onDestroy() {
        stopMtv()
        webView.removeJavascriptInterface("LovKtvNative")
        webView.destroy()
        io.shutdownNow()
        super.onDestroy()
    }
}
