package com.lovktv.phone.feature

import com.lovktv.phone.media.LanMic
import com.lovktv.phone.media.MicService
import com.lovktv.phone.media.NativeMic
import com.lovktv.phone.network.ApiClient
import com.lovktv.phone.network.LanHttp
import com.lovktv.phone.platform.Prefs
import com.lovktv.phone.platform.PhoneBridge
import com.lovktv.phone.room.JoinLink
import com.lovktv.phone.room.RoomConnect
import com.lovktv.phone.ui.DeskPage
import com.lovktv.phone.R

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.KeyEvent
import android.webkit.CookieManager
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
    private var publicFallbackDone = false
    private val watch = Handler(Looper.getMainLooper())
    private var lanMisses = 0
    private var watching = false

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
        startWatch(immediate = lanOrigin.isBlank() && roomCode.isNotBlank())
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
                if (!publicFallbackDone && DeskPage.isLanPage(failed)) {
                    publicFallbackDone = true
                    android.widget.Toast.makeText(
                        this@DeskActivity,
                        getString(R.string.lan_desk_fail),
                        android.widget.Toast.LENGTH_LONG,
                    ).show()
                    view.loadUrl(publicDeskUrl())
                }
            }

            override fun onPageStarted(view: WebView?, url: String?, favicon: android.graphics.Bitmap?) {
                injectLanHttp()
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                injectLanHttp()
                injectRebindEntry()
            }
        }
    }

    private fun loadDesk(hash: String = "", fresh: Boolean = false) {
        var url = DeskPage.url(server, roomCode, lanOrigin)
        if (fresh) url += "&bind=" + System.currentTimeMillis()
        if (hash.isNotBlank()) url += "#$hash"
        webView.stopLoading()
        webView.loadUrl(url)
    }

    fun scanTv() {
        runOnUiThread {
            if (scanning) return@runOnUiThread
            scanning = true
            ScanActivity.start(this)
        }
    }

    fun lanHttp(id: String, url: String, method: String, body: String) {
        Thread({
            val hit = LanHttp.request(url, method, body)
            val payload = org.json.JSONObject()
                .put("id", id)
                .put("ok", hit.ok)
                .put("status", hit.status)
                .put("body", hit.body)
            runOnUiThread {
                if (!::webView.isInitialized) return@runOnUiThread
                webView.evaluateJavascript(
                    "window.LovKtvOnHttp && window.LovKtvOnHttp($payload); window.LovKtvOnLanHttp && window.LovKtvOnLanHttp($payload);",
                    null,
                )
            }
        }, "lovktv-lan-http").start()
    }

    private fun injectLanHttp() {
        webView.evaluateJavascript(
            """
            (function(){
              if (window.__lovktvLanFetch || !window.LovKtvPhone || typeof LovKtvPhone.http !== 'function') return;
              if (typeof window.fetch !== 'function') return;
              window.__lovktvLanFetch = true;
              window.__lovktvLanWait = {};
              window.__lovktvLanSeq = 0;
              window.LovKtvOnLanHttp = function(msg){
                var pending = msg && window.__lovktvLanWait[msg.id];
                if (!pending) return;
                delete window.__lovktvLanWait[msg.id];
                pending(msg);
              };
              function privateHttp(url){
                try {
                  var parsed = new URL(url, location.href);
                  if (parsed.protocol !== 'http:') return false;
                  var host = String(parsed.hostname || '').toLowerCase();
                  if (host === 'localhost' || host.slice(-6) === '.local') return true;
                  var p = host.split('.');
                  if (p.length !== 4) return false;
                  var n = p.map(function(x){ return +x; });
                  if (n.some(function(x){ return x !== x || x < 0 || x > 255; })) return false;
                  return (n[0] === 192 && n[1] === 168) || n[0] === 10 || (n[0] === 172 && n[1] >= 16 && n[1] <= 31);
                } catch (err) { return false; }
              }
              var orig = window.fetch;
              window.fetch = function(input, init){
                var url = typeof input === 'string' ? input : (input && input.url) || '';
                if (!privateHttp(url)) return orig.apply(this, arguments);
                init = init || {};
                var method = String(init.method || 'GET').toUpperCase();
                var body = typeof init.body === 'string' ? init.body : '';
                var id = String(++window.__lovktvLanSeq);
                return new Promise(function(resolve, reject){
                  var timer = setTimeout(function(){
                    delete window.__lovktvLanWait[id];
                    reject(new Error('lan-timeout'));
                  }, 20000);
                  window.__lovktvLanWait[id] = function(msg){
                    clearTimeout(timer);
                    var text = msg && msg.body != null ? String(msg.body) : '';
                    var status = Number(msg && msg.status) || 0;
                    if (typeof Response === 'function') {
                      resolve(new Response(text, { status: status || 599, headers: { 'Content-Type': 'application/json' } }));
                      return;
                    }
                    resolve({
                      ok: !!(msg && msg.ok),
                      status: status,
                      json: function(){ try { return Promise.resolve(JSON.parse(text || '{}')); } catch (err) { return Promise.resolve({}); } }
                    });
                  };
                  try { LovKtvPhone.http(id, url, method, body); }
                  catch (err) { clearTimeout(timer); delete window.__lovktvLanWait[id]; reject(err); }
                });
              };
            })();
            """.trimIndent(),
            null,
        )
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
              // Use semantic mount points from m.html; visual class names are not
              // part of the embedded-page contract and may change with styling.
              wire(ensure('scanTv', '[data-mount="phone-room-sheet"]', '#join', 'btn primary'), label);
              wire(ensure('rebindTv', '[data-mount="phone-who-sheet"]', '[data-mount="phone-language"]', 'btn'), label);
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
            val session = runCatching {
                RoomConnect.open(target.server, target.room, target.lan)
            }.getOrElse {
                RoomConnect.fromQr(target.server, target.room, target.lan)
            }
            runOnUiThread { applySession(session) }
        }, "lovktv-join").start()
    }

    private fun applySession(session: RoomConnect.Session) {
        val micMoved = session.micHost != micHost || session.micPort != micPort
        server = session.server
        roomCode = session.room
        lanOrigin = session.lanOrigin
        micHost = session.micHost
        micPort = session.micPort
        micRate = session.micRate
        Prefs.save(this, server, roomCode, lanOrigin, micHost, micPort, micRate)
        lanMisses = 0
        if (micMoved && MicService.running) {
            MicService.apply(this, micHost, micPort, micRate)
        }
        loadDesk("desk", fresh = true)
        startWatch()
    }

    fun useLan(lan: String, room: String) {
        val code = room.trim().uppercase().ifBlank { roomCode }
        val next = lan.trim().trimEnd('/')
        if (code.isBlank() || next.isBlank()) return
        if (code == roomCode && next.equals(lanOrigin, ignoreCase = true)) return
        Thread({
            val session = runCatching {
                RoomConnect.open(server.ifBlank { Prefs.DEFAULT_SERVER }, code, next)
            }.getOrElse {
                RoomConnect.fromQr(server.ifBlank { Prefs.DEFAULT_SERVER }, code, next)
            }
            runOnUiThread { applySession(session) }
        }, "lovktv-use-lan").start()
    }

    private fun startWatch(immediate: Boolean = false) {
        watching = true
        watch.removeCallbacksAndMessages(null)
        watch.postDelayed({ watchLan() }, if (immediate) 400 else 4000)
    }

    private fun watchLan() {
        if (!watching || roomCode.isBlank()) return
        Thread({
            val current = lanOrigin
            if (current.isNotBlank() && probeTv(current)) {
                val recovered = lanMisses > 0
                lanMisses = 0
                runOnUiThread {
                    if (!watching) return@runOnUiThread
                    if (recovered) {
                        android.widget.Toast.makeText(this, R.string.tv_reconnected, android.widget.Toast.LENGTH_SHORT).show()
                        if (MicService.running) MicService.apply(this, micHost, micPort, micRate)
                    }
                    watch.removeCallbacksAndMessages(null)
                    watch.postDelayed({ watchLan() }, 4000)
                }
                return@Thread
            }
            if (current.isNotBlank()) {
                lanMisses += 1
                if (lanMisses == 1) {
                    runOnUiThread {
                        if (watching) {
                            android.widget.Toast.makeText(this, R.string.tv_reconnecting, android.widget.Toast.LENGTH_SHORT).show()
                        }
                    }
                }
                if (lanMisses < 3) {
                    runOnUiThread {
                        if (watching) {
                            watch.removeCallbacksAndMessages(null)
                            watch.postDelayed({ watchLan() }, 1500)
                        }
                    }
                    return@Thread
                }
            }
            val session = runCatching {
                RoomConnect.open(server.ifBlank { Prefs.DEFAULT_SERVER }, roomCode, "")
            }.getOrNull()
            val nextLan = session?.lanOrigin.orEmpty()
            val live = nextLan.isNotBlank() && probeTv(nextLan)
            runOnUiThread {
                if (!watching) return@runOnUiThread
                if (live && session != null) {
                    if (!nextLan.equals(lanOrigin, ignoreCase = true) || roomCode != session.room) {
                        applySession(session)
                        return@runOnUiThread
                    }
                    lanMisses = 0
                    android.widget.Toast.makeText(this, R.string.tv_reconnected, android.widget.Toast.LENGTH_SHORT).show()
                    if (MicService.running) MicService.apply(this, micHost, micPort, micRate)
                }
                watch.removeCallbacksAndMessages(null)
                watch.postDelayed({ watchLan() }, if (live) 4000 else 2500)
            }
        }, "lovktv-watch").start()
    }

    private fun probeTv(origin: String): Boolean {
        return runCatching {
            ApiClient(origin, 2, 4).host().mode.equals("tv", ignoreCase = true)
        }.getOrDefault(false)
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

    fun appVersionName(): String {
        return try {
            packageManager.getPackageInfo(packageName, 0).versionName.orEmpty()
        } catch (_: Exception) {
            ""
        }
    }

    private fun publicDeskUrl(): String {
        return DeskPage.url(server.ifBlank { Prefs.DEFAULT_SERVER }, roomCode, "")
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

    private fun askPhoneMicPermission() {
        val needed = mutableListOf(Manifest.permission.RECORD_AUDIO)
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            needed.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        requestPermissions(needed.toTypedArray(), REQ_PHONE_MIC)
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
        watching = false
        watch.removeCallbacksAndMessages(null)
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

    companion object {
        const val EXTRA_SERVER = "server"
        const val EXTRA_ROOM = "room"
        const val EXTRA_LAN = "lan"
        const val EXTRA_MIC_HOST = "mic_host"
        const val EXTRA_MIC_PORT = "mic_port"
        const val EXTRA_MIC_RATE = "mic_rate"
        private const val REQ_FILE = 22
        private const val REQ_WEB_MIC = 23
        private const val REQ_PHONE_MIC = 24

        fun hasAudio(activity: Activity): Boolean {
            return activity.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
        }
    }
}
