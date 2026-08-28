package com.lovktv.phone

import java.net.URLDecoder
import java.nio.charset.StandardCharsets

data class JoinTarget(
    val server: String,
    val room: String,
    val lan: String = "",
)

object JoinLink {
    private val ROOM = Regex("^[A-Z0-9]{4,12}$", RegexOption.IGNORE_CASE)
    private val URL = Regex("https?://\\S+", RegexOption.IGNORE_CASE)

    fun parse(raw: String, fallbackServer: String = Prefs.DEFAULT_SERVER): JoinTarget? {
        val text = raw.trim().trim('"', '\'', '“', '”')
        if (text.isEmpty()) return null
        if (ROOM.matches(text)) {
            return JoinTarget(Prefs.normalize(fallbackServer), text.uppercase())
        }
        val url = extractUrl(text) ?: return null
        val server = originOf(url) ?: return null
        val room = queryParam(url, "room").orEmpty().uppercase()
        if (room.isEmpty() || !ROOM.matches(room)) return null
        val lan = queryParam(url, "lan").orEmpty()
        return JoinTarget(
            server = Prefs.normalize(server),
            room = room,
            lan = if (lan.isBlank()) "" else Prefs.normalize(lan),
        )
    }

    private fun extractUrl(text: String): String? {
        val found = URL.find(text)?.value?.trimEnd('/', ')', ']', ',', '.', ';')
        if (found != null) return found
        if (text.contains("room=", ignoreCase = true) ||
            text.contains("m.html", ignoreCase = true) ||
            text.contains("tv.html", ignoreCase = true)
        ) {
            return Prefs.normalize(text)
        }
        return null
    }

    private fun originOf(url: String): String? {
        val value = Prefs.normalize(url)
        val schemeEnd = value.indexOf("://")
        if (schemeEnd <= 0) return null
        val scheme = value.substring(0, schemeEnd)
        val rest = value.substring(schemeEnd + 3)
        val hostPort = rest.substringBefore('/').substringBefore('?').substringBefore('#')
        if (hostPort.isBlank()) return null
        return "$scheme://$hostPort"
    }

    private fun queryParam(url: String, key: String): String? {
        val query = url.substringAfter('?', "").substringBefore('#')
        if (query.isEmpty()) return null
        for (part in query.split('&')) {
            val eq = part.indexOf('=')
            if (eq <= 0) continue
            if (!part.substring(0, eq).equals(key, ignoreCase = true)) continue
            return URLDecoder.decode(part.substring(eq + 1), StandardCharsets.UTF_8.name())
        }
        return null
    }
}
