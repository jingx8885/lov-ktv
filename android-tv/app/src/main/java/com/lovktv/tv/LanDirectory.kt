package com.lovktv.tv

import org.json.JSONObject

object LanDirectory {
    const val HEARTBEAT_MS = 15_000L

    fun shouldPublish(previous: String, next: String, lastAtMs: Long, nowMs: Long, heartbeatMs: Long = HEARTBEAT_MS): Boolean {
        val origin = next.trim().trimEnd('/')
        if (origin.isBlank()) return false
        if (origin != previous.trim().trimEnd('/')) return true
        return lastAtMs <= 0L || nowMs - lastAtMs >= heartbeatMs
    }

    fun publishBody(origin: String, micPort: Int, micSampleRate: Int): String {
        return JSONObject()
            .put("lan_origin", origin.trim().trimEnd('/'))
            .put("local_url", origin.trim().trimEnd('/'))
            .put("mic_port", micPort)
            .put("mic_sample_rate", micSampleRate)
            .toString()
    }

    fun lanFromRoom(json: String): String {
        if (json.isBlank()) return ""
        val obj = JSONObject(json)
        val raw = obj.optString("lan_origin").ifBlank { obj.optString("local_url") }
        return raw.trim().trimEnd('/')
    }
}
