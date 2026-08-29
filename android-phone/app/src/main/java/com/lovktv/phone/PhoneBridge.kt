package com.lovktv.phone

import android.webkit.JavascriptInterface

class PhoneBridge(private val activity: DeskActivity) {
    @JavascriptInterface
    fun capabilities(): String = activity.micCapabilities()

    @JavascriptInterface
    fun state(): String = activity.micStateJson()

    @JavascriptInterface
    fun startTvMic(): String = activity.startNativeMic(send = true, iem = null)

    @JavascriptInterface
    fun stopTvMic(): String = activity.startNativeMic(send = false, iem = null)

    @JavascriptInterface
    fun startIem(): String = activity.startNativeMic(send = null, iem = true)

    @JavascriptInterface
    fun stopIem(): String = activity.startNativeMic(send = null, iem = false)

    @JavascriptInterface
    fun setGain(value: Int) {
        activity.setNativeMicGain(value)
    }

    @JavascriptInterface
    fun scanTv() {
        activity.scanTv()
    }
}
