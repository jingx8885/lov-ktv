package com.lovktv.tv.platform


import android.content.Context

object Prefs {
    const val DEFAULT_SERVER = "https://ktv.lovbrowser.com"
    private const val FILE = "lovktv"
    private const val KEY_SERVER = "server_url"
    private const val KEY_ROOM = "room_code"
    private const val LEGACY_DEFAULT = "http://lov-ktv.local:8787"
    private val ROOM_RE = Regex("^[A-Z0-9]{4,12}$")

    fun serverUrl(context: Context): String {
        return context.getSharedPreferences(FILE, Context.MODE_PRIVATE)
            .getString(KEY_SERVER, "")
            .orEmpty()
    }

    fun migrate(context: Context) {
        val raw = serverUrl(context).trim()
        if (raw.isEmpty() || isLegacyDefault(raw)) {
            saveServer(context, DEFAULT_SERVER)
            return
        }
        val next = normalize(raw)
        if (next != raw) saveServer(context, next)
    }

    fun saveServer(context: Context, raw: String): String {
        val url = normalize(raw)
        context.getSharedPreferences(FILE, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_SERVER, url)
            .apply()
        return url
    }

    fun roomCode(context: Context): String {
        return validRoom(
            context.getSharedPreferences(FILE, Context.MODE_PRIVATE)
                .getString(KEY_ROOM, "")
                .orEmpty(),
        )
    }

    fun saveRoom(context: Context, raw: String): String {
        val code = validRoom(raw)
        if (code.isBlank()) return roomCode(context)
        context.getSharedPreferences(FILE, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_ROOM, code)
            .apply()
        return code
    }

    fun validRoom(raw: String): String {
        val code = raw.trim().uppercase()
        return if (ROOM_RE.matches(code)) code else ""
    }

    fun normalize(raw: String): String {
        var value = raw.trim().trimEnd('/')
        if (value.isEmpty() || isLegacyDefault(value)) {
            return DEFAULT_SERVER
        }
        if (!value.startsWith("http://") && !value.startsWith("https://")) {
            val host = value.substringBefore('/').substringBefore(':')
            val scheme = if (looksLocal(host)) "http" else "https"
            value = "$scheme://$value"
        } else if (value.startsWith("http://")) {
            val host = value.removePrefix("http://").substringBefore('/').substringBefore(':')
            if (!looksLocal(host)) {
                value = "https://" + value.removePrefix("http://")
            }
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

    fun isLegacyDefault(raw: String): Boolean {
        val value = raw.trim().trimEnd('/').lowercase()
        return value == LEGACY_DEFAULT || value == "lov-ktv.local:8787"
    }
}
