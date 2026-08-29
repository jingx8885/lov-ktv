package com.lovktv.tv

sealed class ApiKind {
    data object Host : ApiKind()
    data object SongsList : ApiKind()
    data class Song(val id: String) : ApiKind()
    data object RoomCreate : ApiKind()
    data class RoomGet(val code: String) : ApiKind()
    data class RoomQueue(val code: String) : ApiKind()
    data class RoomBump(val code: String) : ApiKind()
    data class RoomSkip(val code: String) : ApiKind()
    data class RoomPlay(val code: String) : ApiKind()
    data class RoomMix(val code: String) : ApiKind()
    data class Media(val songId: String, val name: String) : ApiKind()
    data object Proxy : ApiKind()
    data object Static : ApiKind()
}

data class HostInfo(
    val origin: String,
    val processOrigin: String,
    val mode: String,
    val phonePath: String,
    val phoneUrl: String,
    val cacheReady: Int = 0,
    val micPort: Int = 0,
    val micSampleRate: Int = LanMic.SAMPLE_RATE,
    val room: String = "",
    val assetRev: String = "",
)

object HostGateway {
    fun phoneUrl(origin: String, room: String, processOrigin: String = ""): String {
        val page = origin.trim().trimEnd('/')
        val code = room.trim().uppercase()
        var url = "$page/m.html?room=$code"
        val process = processOrigin.trim().trimEnd('/')
        if (process.isNotBlank() && !process.equals(page, ignoreCase = true)) {
            url += "&process=" + java.net.URLEncoder.encode(process, "UTF-8")
        }
        return url
    }

    fun isLocalPath(path: String): Boolean {
        val clean = path.substringBefore('?').ifBlank { "/" }
        if (clean == "/api/host") return true
        if (clean.startsWith("/api/") || clean.startsWith("/media/") || clean.startsWith("/ws/")) {
            return false
        }
        return true
    }

    fun remoteUrl(processOrigin: String, path: String, query: String?): String {
        val base = processOrigin.trim().trimEnd('/')
        val suffix = if (path.startsWith("/")) path else "/$path"
        return if (query.isNullOrBlank()) "$base$suffix" else "$base$suffix?$query"
    }

    fun websocketUrl(httpUrl: String): String {
        return when {
            httpUrl.startsWith("https://") -> "wss://" + httpUrl.removePrefix("https://")
            httpUrl.startsWith("http://") -> "ws://" + httpUrl.removePrefix("http://")
            else -> httpUrl
        }
    }

    fun pickLanAddress(addresses: List<String>): String {
        val privateV4 = addresses.map { it.trim() }.filter(::isPrivateIpv4)
        return privateV4.firstOrNull { it.startsWith("192.168.") }
            ?: privateV4.firstOrNull { it.startsWith("10.") }
            ?: privateV4.firstOrNull { is172Private(it) }
            ?: ""
    }

    fun hostPayload(
        lanOrigin: String,
        processOrigin: String,
        room: String = "",
        cacheReady: Int = 0,
        micPort: Int = LanMic.DEFAULT_PORT,
        micSampleRate: Int = LanMic.SAMPLE_RATE,
        assetRev: String = "",
    ): HostInfo {
        val origin = lanOrigin.trim().trimEnd('/')
        val process = processOrigin.trim().trimEnd('/')
        val page = origin.ifBlank { process }
        val code = room.trim().uppercase()
        val phonePath = if (code.isEmpty()) "/m.html?room=" else "/m.html?room=$code"
        val phone = if (code.isEmpty()) {
            val suffix = if (process.isNotBlank() && !process.equals(page, ignoreCase = true)) {
                "?process=${java.net.URLEncoder.encode(process, "UTF-8")}"
            } else {
                ""
            }
            "$page/m.html$suffix"
        } else {
            phoneUrl(page, code, process)
        }
        return HostInfo(
            origin = origin,
            processOrigin = process,
            mode = "tv",
            phonePath = phonePath,
            phoneUrl = phone,
            cacheReady = cacheReady,
            micPort = micPort,
            micSampleRate = micSampleRate,
            room = code,
            assetRev = assetRev,
        )
    }

    fun toJson(info: HostInfo): String {
        return buildString {
            append('{')
            append("\"origin\":").append(quote(info.origin)).append(',')
            append("\"process_origin\":").append(quote(info.processOrigin)).append(',')
            append("\"mode\":").append(quote(info.mode)).append(',')
            append("\"phone_path\":").append(quote(info.phonePath)).append(',')
            append("\"phone_url\":").append(quote(info.phoneUrl)).append(',')
            append("\"cache_ready\":").append(info.cacheReady).append(',')
            append("\"mic_port\":").append(info.micPort).append(',')
            append("\"mic_sample_rate\":").append(info.micSampleRate).append(',')
            append("\"room\":").append(quote(info.room)).append(',')
            append("\"asset_rev\":").append(quote(info.assetRev))
            append('}')
        }
    }

    fun classify(path: String, method: String = "GET"): ApiKind {
        val clean = path.substringBefore('?').ifBlank { "/" }
        val verb = method.uppercase()
        if (clean == "/api/host") return ApiKind.Host
        MediaCache.parsePath(clean)?.let { return ApiKind.Media(it.first, it.second) }
        if (clean == "/api/songs") return if (verb == "GET") ApiKind.SongsList else ApiKind.Proxy
        val song = Regex("^/api/songs/([^/]+)$").matchEntire(clean)
        if (song != null && verb == "GET") return ApiKind.Song(song.groupValues[1])
        if (clean == "/api/rooms" && verb == "GET") return ApiKind.RoomGet("")
        if (clean == "/api/rooms" && verb == "POST") return ApiKind.RoomCreate
        val room = Regex("^/api/rooms/([A-Za-z0-9]+)$").matchEntire(clean)
        if (room != null && verb == "GET") return ApiKind.RoomGet(room.groupValues[1].uppercase())
        val action = Regex("^/api/rooms/([A-Za-z0-9]+)/(queue|bump|skip|play|mix)$").matchEntire(clean)
        if (action != null && verb == "POST") {
            val code = action.groupValues[1].uppercase()
            return when (action.groupValues[2]) {
                "queue" -> ApiKind.RoomQueue(code)
                "bump" -> ApiKind.RoomBump(code)
                "skip" -> ApiKind.RoomSkip(code)
                "play" -> ApiKind.RoomPlay(code)
                else -> ApiKind.RoomMix(code)
            }
        }
        if (clean.startsWith("/api/") || clean.startsWith("/ws/") || clean.startsWith("/media/")) {
            return ApiKind.Proxy
        }
        return ApiKind.Static
    }

    fun isHopByHop(name: String): Boolean {
        return when (name.lowercase()) {
            "connection",
            "keep-alive",
            "proxy-authenticate",
            "proxy-authorization",
            "te",
            "trailers",
            "transfer-encoding",
            "upgrade",
            "host",
            -> true
            else -> false
        }
    }

    private fun isPrivateIpv4(ip: String): Boolean {
        if (ip == "127.0.0.1" || ip.startsWith("169.254.")) return false
        if (ip.startsWith("192.168.") || ip.startsWith("10.")) return true
        return is172Private(ip)
    }

    private fun is172Private(ip: String): Boolean {
        val parts = ip.split('.')
        if (parts.size != 4 || parts[0] != "172") return false
        val second = parts[1].toIntOrNull() ?: return false
        return second in 16..31
    }

    private fun quote(value: String): String {
        val escaped = value.replace("\\", "\\\\").replace("\"", "\\\"")
        return "\"$escaped\""
    }
}
