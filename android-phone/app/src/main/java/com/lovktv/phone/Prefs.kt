package com.lovktv.phone

import android.content.Context

object Prefs {
    const val DEFAULT_SERVER = "https://ktv.lovbrowser.com"
    private const val FILE = "lovktv-phone"
    private const val KEY_SERVER = "server_url"
    private const val KEY_ROOM = "room_code"
    private const val KEY_LAN = "lan_url"
    private const val KEY_MIC_HOST = "mic_host"
    private const val KEY_MIC_PORT = "mic_port"
    private const val KEY_MIC_RATE = "mic_rate"

    fun serverUrl(context: Context): String {
        return context.getSharedPreferences(FILE, Context.MODE_PRIVATE)
            .getString(KEY_SERVER, "")
            .orEmpty()
    }

    fun roomCode(context: Context): String {
        return context.getSharedPreferences(FILE, Context.MODE_PRIVATE)
            .getString(KEY_ROOM, "")
            .orEmpty()
    }

    fun lanUrl(context: Context): String {
        return context.getSharedPreferences(FILE, Context.MODE_PRIVATE)
            .getString(KEY_LAN, "")
            .orEmpty()
    }

    fun micHost(context: Context): String {
        return context.getSharedPreferences(FILE, Context.MODE_PRIVATE)
            .getString(KEY_MIC_HOST, "")
            .orEmpty()
    }

    fun micPort(context: Context): Int {
        return context.getSharedPreferences(FILE, Context.MODE_PRIVATE)
            .getInt(KEY_MIC_PORT, 0)
    }

    fun micRate(context: Context): Int {
        val rate = context.getSharedPreferences(FILE, Context.MODE_PRIVATE)
            .getInt(KEY_MIC_RATE, LanMic.SAMPLE_RATE)
        return if (rate in 8000..96000) rate else LanMic.SAMPLE_RATE
    }

    fun save(
        context: Context,
        server: String,
        room: String,
        lan: String = "",
        micHost: String = "",
        micPort: Int = 0,
        micRate: Int = LanMic.SAMPLE_RATE,
    ) {
        context.getSharedPreferences(FILE, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_SERVER, normalize(server))
            .putString(KEY_ROOM, room.trim().uppercase())
            .putString(KEY_LAN, if (lan.isBlank()) "" else normalize(lan))
            .putString(KEY_MIC_HOST, micHost.trim())
            .putInt(KEY_MIC_PORT, micPort)
            .putInt(KEY_MIC_RATE, if (micRate in 8000..96000) micRate else LanMic.SAMPLE_RATE)
            .apply()
    }

    fun normalize(raw: String): String {
        var value = raw.trim().trimEnd('/')
        if (value.isEmpty()) {
            value = DEFAULT_SERVER
        }
        if (!value.startsWith("http://") && !value.startsWith("https://")) {
            val host = value.substringBefore('/').substringBefore(':')
            val scheme = if (looksLocal(host)) "http" else "https"
            value = "$scheme://$value"
        }
        return value
    }

    fun looksLocal(host: String): Boolean {
        val name = host.trim().lowercase()
        if (name == "localhost" || name.endsWith(".local")) return true
        val parts = name.split('.')
        if (parts.size != 4) return false
        val nums = parts.map { it.toIntOrNull() ?: return false }
        if (nums.any { it !in 0..255 }) return false
        if (nums[0] == 192 && nums[1] == 168) return true
        if (nums[0] == 10) return true
        if (nums[0] == 172 && nums[1] in 16..31) return true
        return false
    }
}
