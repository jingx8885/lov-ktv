package com.lovktv.tv

import android.content.Context

object Prefs {
    const val DEFAULT_SERVER = "http://lov-ktv.local:8787"
    private const val FILE = "lovktv"
    private const val KEY_SERVER = "server_url"

    fun serverUrl(context: Context): String {
        return context.getSharedPreferences(FILE, Context.MODE_PRIVATE)
            .getString(KEY_SERVER, "")
            .orEmpty()
    }

    fun saveServer(context: Context, raw: String): String {
        val url = normalize(raw)
        context.getSharedPreferences(FILE, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_SERVER, url)
            .apply()
        return url
    }

    fun normalize(raw: String): String {
        var value = raw.trim().trimEnd('/')
        if (value.isEmpty()) {
            value = DEFAULT_SERVER
        }
        if (!value.startsWith("http://") && !value.startsWith("https://")) {
            value = "http://$value"
        }
        return value
    }
}
