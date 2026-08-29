package com.lovktv.tv.ui


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
    fun openSetup()
}
