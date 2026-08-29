package com.lovktv.phone.ui

import com.lovktv.phone.platform.Prefs

object DeskPage {
    fun url(server: String, room: String, lan: String = ""): String {
        val page = pageOrigin(server)
        val lanOrigin = lanOrigin(server, lan)
        val code = room.trim().uppercase()
        var url = "$page/m.html?room=$code&androidphone=1"
        if (lanOrigin.isNotBlank() && !lanOrigin.equals(page, ignoreCase = true)) {
            url += "&lan=" + java.net.URLEncoder.encode(lanOrigin, "UTF-8")
        }
        return url
    }

    fun pageOrigin(server: String): String {
        val catalog = Prefs.normalize(server.ifBlank { Prefs.DEFAULT_SERVER })
        return if (Prefs.looksLocal(hostOf(catalog))) Prefs.DEFAULT_SERVER else catalog
    }

    fun lanOrigin(server: String, lan: String = ""): String {
        val rawLan = lan.trim().trimEnd('/')
        if (rawLan.isNotBlank()) return Prefs.normalize(rawLan)
        val catalog = server.trim().trimEnd('/')
        if (catalog.isBlank()) return ""
        val normalized = Prefs.normalize(catalog)
        return if (Prefs.looksLocal(hostOf(normalized))) normalized else ""
    }

    fun isLanPage(url: String): Boolean {
        val host = hostOf(url.trim())
        return host.isNotBlank() && Prefs.looksLocal(host)
    }

    fun hostOf(origin: String): String {
        val value = origin.trim()
        if (value.isEmpty()) return ""
        return try {
            val withScheme = if (value.contains("://")) value else "http://$value"
            java.net.URI(withScheme).host?.trim().orEmpty().ifBlank {
                value.substringAfter("://").substringBefore('/').substringBefore(':')
            }
        } catch (_: Exception) {
            value.substringAfter("://").substringBefore('/').substringBefore(':')
        }
    }
}
