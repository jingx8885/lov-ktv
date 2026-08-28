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
        return if (host.mode.equals("tv", ignoreCase = true) && process.isNotBlank()) {
            Prefs.normalize(process)
        } else {
            scanned
        }
    }

    fun pickMic(vararg hosts: HostInfo?): HostInfo? {
        return hosts.firstOrNull { it != null && HostParser.lanMicReady(it) }
    }

    fun open(serverRaw: String, roomRaw: String, lanRaw: String = ""): Session {
        val scanned = Prefs.normalize(serverRaw)
        val lanHint = lanRaw.trim().let { if (it.isBlank()) "" else Prefs.normalize(it) }
        val code = roomRaw.trim().uppercase()
        if (code.isEmpty()) throw IllegalArgumentException("先填房间码")
        val scannedHost = ApiClient(scanned).host()
        val catalog = catalogServer(scanned, scannedHost)
        val lanUrl = when {
            lanHint.isNotBlank() -> lanHint
            HostParser.lanMicReady(scannedHost) -> scanned
            else -> ""
        }
        val lanHost = when {
            lanUrl.isBlank() -> null
            lanUrl == scanned -> scannedHost
            else -> runCatching { ApiClient(lanUrl).host() }.getOrNull()
        }
        val mic = pickMic(lanHost, scannedHost)
        ApiClient(catalog).room(code)
        return Session(
            server = catalog,
            room = code,
            micHost = mic?.let { HostParser.hostFromOrigin(it.origin) }.orEmpty(),
            micPort = if (mic != null && HostParser.lanMicReady(mic)) mic.micPort else 0,
            micRate = mic?.micSampleRate ?: LanMic.SAMPLE_RATE,
            lanOrigin = lanUrl,
        )
    }
}
