package com.lovktv.phone

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Build
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
    private var pendingSend: Boolean? = null
    private var pendingIem: Boolean? = null
    private var scanning = false

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_desk)
        server = intent.getStringExtra(EXTRA_SERVER).orEmpty().ifBlank { Prefs.serverUrl(this) }
        roomCode = intent.getStringExtra(EXTRA_ROOM).orEmpty().ifBlank { Prefs.roomCode(this) }
        lanOrigin = intent.getStringExtra(EXTRA_LAN).orEmpty().ifBlank { Prefs.lanUrl(this) }
        micHost = intent.getStringExtra(EXTRA_MIC_HOST).orEmpty().ifBlank { Prefs.micHost(this) }
        micPort = intent.getIntExtra(EXTRA_MIC_PORT, 0).takeIf { it in 1..65535 } ?: Prefs.micPort(this)
        micRate = intent.getIntExtra(EXTRA_MIC_RATE, 0).takeIf { it in 8000..96000 } ?: Prefs.micRate(this)
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
            cacheMode = WebSettings.LOAD_NO_CACHE
            useWideViewPort = true
            loadWithOverviewMode = true
            builtInZoomControls = false
            displayZoomControls = false
            userAgentString = "$userAgentString LovKtvAndroidPhone/1.0"
        }
        webView.addJavascriptInterface(NativeBridge(), "LovKtvNative")
        webView.addJavascriptInterface(PhoneBridge(this), "LovKtvPhone")
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
                    android.widget.Toast.makeText(
                        this@DeskActivity,
                        getString(R.string.lan_desk_fail),
                        android.widget.Toast.LENGTH_LONG,
                    ).show()
                    view.loadDataWithBaseURL(
                        lanOrigin,
                        lanFailHtml(),
                        "text/html",
                        "utf-8",
                        null,
                    )
                }
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                injectRebindEntry()
            }
        }
    }

    private fun loadDesk(hash: String = "") {
        var url = DeskPage.url(server, roomCode, lanOrigin)
        if (hash.isNotBlank()) url += "#$hash"
        webView.loadUrl(url)
    }

    fun scanTv() {
        runOnUiThread {
            if (scanning) return@runOnUiThread
            scanning = true
            ScanActivity.start(this)
        }
    }

    private fun injectRebindEntry() {
        val bind = org.json.JSONObject.quote(getString(R.string.scan_bind))
        val rebind = org.json.JSONObject.quote(getString(R.string.scan_rebind))
        webView.evaluateJavascript(
            """
            (function(){
              if (!window.LovKtvPhone || typeof LovKtvPhone.scanTv !== 'function') return;
              var q = new URLSearchParams(location.search || '');
              var bound = !!(q.get('process') || q.get('lan'));
              var host = String(location.hostname || '');
              if (!bound) {
                var p = host.split('.');
                bound = host === 'localhost' || host.slice(-6) === '.local' ||
                  (p.length === 4 && ((p[0] === '192' && p[1] === '168') || p[0] === '10' ||
                    (p[0] === '172' && +p[1] >= 16 && +p[1] <= 31)));
              }
              function ensure(id, parentSel, beforeSel, cls) {
                var el = document.getElementById(id);
                if (el) return el;
                var parent = document.querySelector(parentSel);
                if (!parent) return null;
                el = document.createElement('button');
                el.id = id;
                el.type = 'button';
                el.className = cls;
                var before = beforeSel ? parent.querySelector(beforeSel) : null;
                parent.insertBefore(el, before);
                return el;
              }
              function wire(el, label) {
                if (!el) return;
                el.hidden = false;
                el.textContent = label;
                el.onclick = function(){ LovKtvPhone.scanTv(); };
              }
              var label = bound ? $rebind : $bind;
              wire(ensure('scanTv', '#roomSheet .sheet', '#join', 'btn primary'), label);
              wire(ensure('rebindTv', '#whoSheet .sheet', '.lang-picker', 'btn'), label);
            })();
            """.trimIndent(),
            null,
        )
    }

    private fun joinFromScan(text: String) {
        val target = JoinLink.parse(text)
        if (target == null) {
            android.widget.Toast.makeText(this, R.string.scan_invalid, android.widget.Toast.LENGTH_LONG).show()
            return
        }
        android.widget.Toast.makeText(this, R.string.scan_joining, android.widget.Toast.LENGTH_SHORT).show()
        Thread({
            try {
                val session = RoomConnect.open(target.server, target.room, target.lan)
                runOnUiThread { applySession(session) }
            } catch (exc: Exception) {
                runOnUiThread {
                    android.widget.Toast.makeText(
                        this,
                        exc.message ?: getString(R.string.scan_invalid),
                        android.widget.Toast.LENGTH_LONG,
                    ).show()
                }
            }
        }, "lovktv-join").start()
    }

    private fun applySession(session: RoomConnect.Session) {
        server = session.server
        roomCode = session.room
        lanOrigin = session.lanOrigin
        micHost = session.micHost
        micPort = session.micPort
        micRate = session.micRate
        Prefs.save(this, server, roomCode, lanOrigin, micHost, micPort, micRate)
        loadDesk("desk")
    }

    fun micCapabilities(): String = NativeMic.capabilitiesJson(micHost, micPort, micRate)

    fun micStateJson(): String = NativeMic.stateJson(
        MicService.sendEnabled && MicService.live,
        MicService.iemEnabled && MicService.live,
        MicService.gainPct,
    )

    fun startNativeMic(send: Boolean?, iem: Boolean?): String {
        if (send == true && !hasLanMic()) return "no-tv"
        if (!hasAudio(this)) {
            pendingSend = send
            pendingIem = iem
            runOnUiThread { askPhoneMicPermission() }
            return "ask"
        }
        MicService.apply(this, micHost, micPort, micRate, send = send, iem = iem)
        return "ok"
    }

    fun setNativeMicGain(value: Int) {
        MicService.apply(this, micHost, micPort, micRate, gain = value)
    }

    private fun lanFailHtml(): String {
        val msg = getString(R.string.lan_desk_fail)
        val retry = getString(R.string.lan_desk_retry)
        val href = DeskPage.url(server, roomCode, lanOrigin)
        return """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{margin:0;min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;background:#0B1020;color:#f4f1ea;font-family:sans-serif;padding:24px;text-align:center}a{color:#ffd6a0}</style>
</head><body><p>$msg</p><p><a href="$href">$retry</a></p></body></html>"""
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

    private fun askPhoneMicPermission() {
        val needed = mutableListOf(Manifest.permission.RECORD_AUDIO)
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            needed.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        requestPermissions(needed.toTypedArray(), REQ_PHONE_MIC)
    }

    private fun notifyJs(ok: Boolean, err: String) {
        if (!::webView.isInitialized) return
        val safe = err.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")
        webView.evaluateJavascript(
            "window.LovKtvOnMic && window.LovKtvOnMic(${if (ok) "true" else "false"}, '$safe')",
            null,
        )
    }

    private fun dispatchMicEvent(name: String) {
        webView.evaluateJavascript(
            "window.dispatchEvent(new Event('$name'));",
            null,
        )
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
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
            REQ_PHONE_MIC -> {
                if (granted && hasAudio(this)) {
                    val send = pendingSend
                    val iem = pendingIem
                    pendingSend = null
                    pendingIem = null
                    if (send != null || iem != null) {
                        MicService.apply(this, micHost, micPort, micRate, send = send, iem = iem)
                    }
                    dispatchMicEvent("lovktv-mic-granted")
                } else {
                    pendingSend = null
                    pendingIem = null
                    dispatchMicEvent("lovktv-mic-denied")
                }
            }
        }
    }

    override fun onDestroy() {
        pendingWebPerm?.deny()
        pendingWebPerm = null
        fileCallback?.onReceiveValue(null)
        fileCallback = null
        if (!isChangingConfigurations) {
            MicService.stop(this)
        }
        webView.destroy()
        super.onDestroy()
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == ScanActivity.REQ) {
            scanning = false
            if (resultCode != RESULT_OK) {
                dispatchMicEvent("lovktv-scan-cancel")
                return
            }
            joinFromScan(data?.getStringExtra(ScanActivity.EXTRA_TEXT).orEmpty())
            return
        }
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
        private const val REQ_PHONE_MIC = 25

        fun hasAudio(activity: Activity): Boolean {
            return activity.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
        }
    }
}
