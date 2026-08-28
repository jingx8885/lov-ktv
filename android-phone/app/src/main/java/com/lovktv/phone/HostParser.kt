package com.lovktv.phone

import org.json.JSONObject

data class HostInfo(
    val origin: String,
    val processOrigin: String,
    val mode: String,
    val micPort: Int,
    val micSampleRate: Int,
)

object HostParser {
    fun parse(json: String): HostInfo {
        val obj = JSONObject(json)
        return HostInfo(
            origin = obj.optString("origin").trim().trimEnd('/'),
            processOrigin = obj.optString("process_origin").trim().trimEnd('/'),
            mode = obj.optString("mode"),
            micPort = obj.optInt("mic_port", 0),
            micSampleRate = obj.optInt("mic_sample_rate", LanMic.SAMPLE_RATE).takeIf { it in 8000..96000 }
                ?: LanMic.SAMPLE_RATE,
        )
    }

    fun hostFromOrigin(origin: String): String {
        val raw = origin.trim()
        val noScheme = raw.substringAfter("://", raw)
        return noScheme.substringBefore('/').substringBefore(':')
    }

    fun lanMicReady(info: HostInfo): Boolean {
        return info.mode.equals("tv", ignoreCase = true) &&
            info.micPort in 1..65535 &&
            hostFromOrigin(info.origin).isNotBlank()
    }
}
