package com.lovktv.phone

object RoomConnect {
    data class Session(
        val server: String,
        val room: String,
        val micHost: String,
        val micPort: Int,
        val micRate: Int,
        val lanOrigin: String = "",
    )

    fun catalogServer(scanned: String, host: HostInfo): String {
        val process = host.processOrigin.trim().trimEnd('/')
        if (host.mode.equals("tv", ignoreCase = true) && process.isNotBlank()) {
            return Prefs.normalize(process)
        }
        val picked = Prefs.normalize(scanned)
        return if (Prefs.looksLocal(HostParser.hostFromOrigin(picked))) Prefs.DEFAULT_SERVER else picked
    }

    fun lanOrigin(scanned: String, lanHint: String, host: HostInfo): String {
        if (lanHint.isNotBlank()) return Prefs.normalize(lanHint)
        if (Prefs.looksLocal(HostParser.hostFromOrigin(scanned))) return Prefs.normalize(scanned)
        if (host.mode.equals("tv", ignoreCase = true) && host.origin.isNotBlank()) {
            return Prefs.normalize(host.origin)
        }
        return ""
    }

    fun roomOrigin(catalog: String, lan: String): String {
        return if (lan.isNotBlank()) lan else catalog
    }

    fun pickMic(vararg hosts: HostInfo?): HostInfo? {
        return hosts.firstOrNull { it != null && HostParser.lanMicReady(it) }
    }

    fun fromQr(
        serverRaw: String,
        roomRaw: String,
        lanRaw: String = "",
        boxHost: HostInfo? = null,
        lanHost: HostInfo? = null,
    ): Session {
        val scanned = Prefs.normalize(serverRaw)
        val lanHint = lanRaw.trim().let { if (it.isBlank()) "" else Prefs.normalize(it) }
        val code = roomRaw.trim().uppercase()
        if (code.isEmpty()) throw IllegalArgumentException("先填房间码")
        val catalog = if (boxHost != null) {
            catalogServer(scanned, boxHost)
        } else if (Prefs.looksLocal(HostParser.hostFromOrigin(scanned))) {
            Prefs.DEFAULT_SERVER
        } else {
            scanned
        }
        val lanUrl = if (boxHost != null) {
            lanOrigin(scanned, lanHint, boxHost)
        } else when {
            lanHint.isNotBlank() -> lanHint
            Prefs.looksLocal(HostParser.hostFromOrigin(scanned)) -> scanned
            else -> ""
        }
        val mic = pickMic(lanHost, boxHost)
        return Session(
            server = catalog,
            room = code,
            micHost = mic?.let { HostParser.hostFromOrigin(it.origin) }.orEmpty()
                .ifBlank { if (lanUrl.isNotBlank()) DeskPage.hostOf(lanUrl) else "" },
            micPort = if (mic != null && HostParser.lanMicReady(mic)) mic.micPort else 0,
            micRate = mic?.micSampleRate ?: LanMic.SAMPLE_RATE,
            lanOrigin = lanUrl,
        )
    }

    fun open(serverRaw: String, roomRaw: String, lanRaw: String = ""): Session {
        val scanned = Prefs.normalize(serverRaw)
        val lanHint = lanRaw.trim().let { if (it.isBlank()) "" else Prefs.normalize(it) }
        val code = roomRaw.trim().uppercase()
        if (code.isEmpty()) throw IllegalArgumentException("先填房间码")
        val lanGuess = when {
            lanHint.isNotBlank() -> lanHint
            Prefs.looksLocal(HostParser.hostFromOrigin(scanned)) -> scanned
            else -> ""
        }
        val boxUrl = lanGuess.ifBlank { scanned }
        val boxHost = runCatching { ApiClient(boxUrl).host() }.getOrNull()
        val lanUrl = if (boxHost != null) lanOrigin(scanned, lanHint, boxHost) else lanGuess
        val lanHost = when {
            lanUrl.isBlank() -> null
            boxHost != null && lanUrl == boxUrl -> boxHost
            else -> runCatching { ApiClient(lanUrl).host() }.getOrNull()
        }
        return fromQr(scanned, code, lanHint, boxHost, lanHost)
    }
}
