package com.lovktv.phone

object NativeMic {
    fun canStart(host: String, port: Int): Boolean {
        return host.isNotBlank() && port in 1..65535
    }

    fun capabilitiesJson(host: String, port: Int, rate: Int): String {
        val tv = canStart(host, port)
        return buildString {
            append("{\"native\":true")
            append(",\"tv\":").append(tv)
            append(",\"iem\":true")
            append(",\"scan\":true")
            append(",\"host\":").append(quote(host))
            append(",\"port\":").append(if (tv) port else 0)
            append(",\"rate\":").append(rate)
            append('}')
        }
    }

    fun stateJson(tv: Boolean, iem: Boolean, gain: Int): String {
        return "{\"tv\":$tv,\"iem\":$iem,\"gain\":${gain.coerceIn(0, 100)}}"
    }

    fun quote(value: String): String {
        val escaped = value.replace("\\", "\\\\").replace("\"", "\\\"")
        return "\"$escaped\""
    }

    fun scalePcm(pcm: ByteArray, length: Int, gainPct: Int) {
        val g = gainPct.coerceIn(0, 100)
        if (g >= 100 || length < 2) return
        var i = 0
        while (i + 1 < length) {
            val sample = ((pcm[i + 1].toInt() shl 8) or (pcm[i].toInt() and 0xFF)).toShort().toInt()
            val next = (sample * g / 100).coerceIn(-32768, 32767)
            pcm[i] = (next and 0xFF).toByte()
            pcm[i + 1] = ((next shr 8) and 0xFF).toByte()
            i += 2
        }
    }
}
