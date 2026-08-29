package com.lovktv.phone

object DeskPage {
    fun url(server: String, room: String, lan: String = ""): String {
        val catalog = server.trim().trimEnd('/')
        val lanOrigin = lan.trim().trimEnd('/')
        val code = room.trim().uppercase()
        val base = if (lanOrigin.isNotBlank()) lanOrigin else catalog.ifBlank { Prefs.DEFAULT_SERVER }
        var url = "$base/m.html?room=$code&v=scan2&androidphone=1"
        if (lanOrigin.isNotBlank() && catalog.isNotBlank() && !lanOrigin.equals(catalog, ignoreCase = true)) {
            url += "&process=" + java.net.URLEncoder.encode(catalog, "UTF-8")
        }
        return url
    }
}
