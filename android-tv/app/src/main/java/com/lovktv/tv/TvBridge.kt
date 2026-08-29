package com.lovktv.tv

import android.webkit.JavascriptInterface

class TvBridge(private val host: TvHost) {
    @JavascriptInterface
    fun playMtv(url: String) {
        host.runOnUi { host.playMtv(url) }
    }

    @JavascriptInterface
    fun stopMtv() {
        host.runOnUi { host.stopMtv() }
    }

    @JavascriptInterface
    fun pauseMtv() {
        host.runOnUi { host.pauseMtv() }
    }

    @JavascriptInterface
    fun resumeMtv() {
        host.runOnUi { host.resumeMtv() }
    }

    @JavascriptInterface
    fun seekMtv(ms: Double) {
        host.runOnUi { host.seekMtv(ms.toInt()) }
    }

    @JavascriptInterface
    fun positionMs(): Int = host.mtvPositionMs()

    @JavascriptInterface
    fun durationMs(): Int = host.mtvDurationMs()

    @JavascriptInterface
    fun playing(): Boolean = host.mtvPlaying()

    @JavascriptInterface
    fun setCover(url: String) {
        host.runOnUi { host.showCover(url) }
    }

    @JavascriptInterface
    fun setLyrics(cur: String, zh: String, next: String) {
        host.runOnUi { host.showLyrics("", "", "") }
    }

    @JavascriptInterface
    fun clearLyrics() {
        host.runOnUi { host.showLyrics("", "", "") }
    }

    @JavascriptInterface
    fun openSetup() {
        host.runOnUi { host.openSetup() }
    }
}

interface TvHost {
    fun runOnUi(block: () -> Unit)
    fun playMtv(url: String)
    fun stopMtv()
    fun pauseMtv()
    fun resumeMtv()
    fun seekMtv(ms: Int)
    fun mtvPositionMs(): Int
    fun mtvDurationMs(): Int
    fun mtvPlaying(): Boolean
    fun showCover(url: String)
    fun showLyrics(cur: String, zh: String, next: String)
    fun openSetup()
}

object LyricOverlay {
    fun visibleText(cur: String, zh: String): String {
        val main = cur.trim()
        val trans = zh.trim()
        if (main.isEmpty()) return trans
        if (trans.isEmpty() || trans == main) return main
        return "$main\n$trans"
    }
}
