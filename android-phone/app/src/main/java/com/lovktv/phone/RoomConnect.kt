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

    fun lanFromRoom(room: RoomView?): String {
        val lan = room?.lanOrigin.orEmpty().trim().trimEnd('/')
        if (lan.isBlank()) return ""
        return if (Prefs.looksLocal(HostParser.hostFromOrigin(lan))) Prefs.normalize(lan) else ""
    }

    fun catalogOf(scanned: String): String {
        val picked = Prefs.normalize(scanned)
        return if (Prefs.looksLocal(HostParser.hostFromOrigin(picked))) Prefs.DEFAULT_SERVER else picked
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
        val catalog = catalogOf(scanned)
        val cloudRoom = if (Prefs.looksLocal(HostParser.hostFromOrigin(scanned))) {
            null
        } else {
            runCatching { ApiClient(catalog, 4, 8).room(code) }.getOrNull()
        }
        val discovered = lanFromRoom(cloudRoom)
        val lanGuess = when {
            lanHint.isNotBlank() -> lanHint
            Prefs.looksLocal(HostParser.hostFromOrigin(scanned)) -> scanned
            discovered.isNotBlank() -> discovered
            else -> ""
        }
        val boxUrl = lanGuess.ifBlank { scanned }
        val boxHost = runCatching { ApiClient(boxUrl, 2, 4).host() }.getOrNull()
        val resolvedHint = lanGuess.ifBlank { lanHint }
        val lanUrl = if (boxHost != null) lanOrigin(scanned, resolvedHint, boxHost) else lanGuess
        val lanHost = when {
            lanUrl.isBlank() -> null
            boxHost != null && lanUrl == boxUrl -> boxHost
            else -> runCatching { ApiClient(lanUrl, 2, 4).host() }.getOrNull()
        }
        val session = fromQr(scanned, code, resolvedHint, boxHost, lanHost)
        val cloudLan = discovered.ifBlank { session.lanOrigin }
        return session.copy(
            lanOrigin = session.lanOrigin.ifBlank { cloudLan },
            micHost = session.micHost.ifBlank {
                val origin = session.lanOrigin.ifBlank { cloudLan }
                if (origin.isNotBlank()) DeskPage.hostOf(origin) else ""
            },
            micPort = session.micPort.takeIf { it in 1..65535 } ?: (cloudRoom?.lanMicPort ?: 0),
            micRate = if (session.micPort in 1..65535) session.micRate else (cloudRoom?.lanMicRate ?: LanMic.SAMPLE_RATE),
        )
    }
}
