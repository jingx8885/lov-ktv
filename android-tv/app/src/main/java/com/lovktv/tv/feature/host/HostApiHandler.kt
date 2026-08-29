package com.lovktv.tv.feature.host


import com.lovktv.tv.media.MediaCache
import com.lovktv.tv.network.SongPuller
import com.lovktv.tv.room.LocalRoom
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.server.application.ApplicationCall
import io.ktor.server.request.httpMethod
import io.ktor.server.request.path
import io.ktor.server.request.queryString
import io.ktor.server.request.receive
import io.ktor.server.response.respond
import io.ktor.server.response.respondBytes
import io.ktor.server.response.respondText
import io.ktor.utils.io.ByteWriteChannel
import io.ktor.utils.io.writeFully
import io.ktor.http.content.OutgoingContent
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

/** Implements API proxying plus the local room/catalog fallback. */
class HostApiHandler(
    private val cache: MediaCache,
    private val localRoom: LocalRoom,
    private val puller: SongPuller,
    private val apiHttp: OkHttpClient,
    private val http: OkHttpClient,
    private val processOrigin: () -> String,
    private val lanOrigin: () -> String,
    private val rememberCode: (String) -> Unit,
    private val broadcast: (String, String) -> Unit,
) {
    suspend fun handle(call: ApplicationCall, kind: ApiKind) {
        val method = call.request.httpMethod.value
        val incoming = if (method == "GET" || method == "HEAD") ByteArray(0) else call.receive<ByteArray>()
        val localRoomApi = kind is ApiKind.RoomCreate || kind is ApiKind.RoomGet || kind is ApiKind.RoomQueue ||
            kind is ApiKind.RoomBump || kind is ApiKind.RoomSkip || kind is ApiKind.RoomPlay || kind is ApiKind.RoomMix
        if (localRoomApi) {
            try {
                val json = fallbackJson(kind, incoming)
                runCatching { rememberCode(JSONObject(json).optString("code")) }
                call.response.headers.append(HttpHeaders.CacheControl, "no-store")
                call.response.headers.append("Access-Control-Allow-Origin", "*")
                call.respondText(json, ContentType.Application.Json)
                if (kind is ApiKind.RoomQueue || kind is ApiKind.RoomPlay) puller.hint()
                if (kind !is ApiKind.RoomGet) {
                    val code = JSONObject(json).optString("code")
                    if (code.isNotBlank()) broadcast(code, json)
                }
            } catch (exc: IllegalArgumentException) {
                val status = if (exc.message == "歌曲不存在") HttpStatusCode.NotFound else HttpStatusCode.BadRequest
                call.respond(status, exc.message ?: "bad request")
            }
            return
        }
        val buffered = kind is ApiKind.SongsList || kind is ApiKind.Song
        if (buffered) {
            val remote = withContext(Dispatchers.IO) { fetchApi(call, incoming) }
            if (remote != null) {
                rememberRemote(kind, remote)
                call.respondBytes(remote, ContentType.Application.Json)
                return
            }
            try {
                call.respondText(fallbackJson(kind, incoming), ContentType.Application.Json)
            } catch (exc: IllegalArgumentException) {
                val status = if (exc.message == "歌曲不存在") HttpStatusCode.NotFound else HttpStatusCode.BadRequest
                call.respond(status, exc.message ?: "bad request")
            }
            return
        }
        proxyHttp(call, incoming)
    }

    suspend fun proxy(call: ApplicationCall) {
        val method = call.request.httpMethod.value
        val incoming = if (method == "GET" || method == "HEAD") ByteArray(0) else call.receive<ByteArray>()
        proxyHttp(call, incoming)
    }

    private fun rememberRemote(kind: ApiKind, body: ByteArray) {
        val text = body.toString(Charsets.UTF_8)
        if (text.isBlank()) return
        when (kind) {
            is ApiKind.RoomGet, is ApiKind.RoomQueue, is ApiKind.RoomBump, is ApiKind.RoomSkip,
            is ApiKind.RoomPlay, is ApiKind.RoomMix, ApiKind.RoomCreate -> {
                runCatching { localRoom.importSnapshot(text) }
                runCatching { rememberCode(JSONObject(text).optString("code")) }
            }
            ApiKind.SongsList, is ApiKind.Song -> puller.hint()
            else -> Unit
        }
    }

    private fun fallbackJson(kind: ApiKind, incoming: ByteArray): String {
        val payload = incoming.toString(Charsets.UTF_8).ifBlank { "{}" }
        val obj = runCatching { JSONObject(payload) }.getOrElse { JSONObject() }
        return when (kind) {
            ApiKind.SongsList -> cache.catalogJson()
            is ApiKind.Song -> cache.songJson(kind.id) ?: throw IllegalArgumentException("歌曲不存在")
            ApiKind.RoomCreate -> {
                val wanted = obj.optString("code").ifBlank { HostRuntime.roomCode }.ifBlank { null }
                localRoom.ensure(wanted).toJson()
            }
            is ApiKind.RoomGet -> localRoom.snapshot(kind.code).toJson()
            is ApiKind.RoomQueue -> localRoom.enqueue(kind.code, obj.optString("song_id")).toJson()
            is ApiKind.RoomBump -> localRoom.bump(kind.code, obj.optString("id")).toJson()
            is ApiKind.RoomSkip -> localRoom.skip(kind.code).toJson()
            is ApiKind.RoomPlay -> localRoom.playNow(kind.code, obj.optString("id"), obj.optString("song_id")).toJson()
            is ApiKind.RoomMix -> localRoom.setMix(
                kind.code,
                vocalMix = if (obj.has("vocal_mix")) obj.optDouble("vocal_mix") else null,
                volume = if (obj.has("volume")) obj.optInt("volume") else null,
                micGain = if (obj.has("mic_gain")) obj.optInt("mic_gain") else null,
                paused = when {
                    !obj.has("paused") || obj.isNull("paused") -> null
                    obj.get("paused") is Number -> obj.optInt("paused") != 0
                    else -> obj.optBoolean("paused")
                },
            ).toJson()
            else -> throw IllegalArgumentException("处理服务器暂时连不上")
        }
    }

    private fun fetchApi(call: ApplicationCall, incoming: ByteArray): ByteArray? {
        return try {
            val remote = HostGateway.remoteUrl(processOrigin(), call.request.path(), call.request.queryString().ifBlank { null })
            val method = call.request.httpMethod.value
            val mediaType = "application/json; charset=utf-8".toMediaTypeOrNull()
            val body: RequestBody? = if (method == "GET" || method == "HEAD") null else incoming.toRequestBody(mediaType)
            val request = Request.Builder().url(remote).method(method, body)
                .header("Accept", "application/json").header("User-Agent", "LovKtv-TV/1.0").build()
            apiHttp.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    android.util.Log.w("HostApiHandler", "fetchApi ${call.request.path()} -> ${response.code}")
                    return null
                }
                response.body?.bytes()
            }
        } catch (exc: Exception) {
            android.util.Log.w("HostApiHandler", "fetchApi ${call.request.path()} failed: ${exc.message}")
            null
        }
    }

    private suspend fun proxyHttp(call: ApplicationCall, incoming: ByteArray) {
        val remote = HostGateway.remoteUrl(processOrigin(), call.request.path(), call.request.queryString().ifBlank { null })
        val method = call.request.httpMethod.value
        val mediaType = call.request.headers[HttpHeaders.ContentType]?.toMediaTypeOrNull()
        val body: RequestBody? = if (method == "GET" || method == "HEAD") null else incoming.toRequestBody(mediaType)
        val builder = Request.Builder().url(remote).method(method, body)
        copyHeaders(call, builder)
        val response = withContext(Dispatchers.IO) { http.newCall(builder.build()).execute() }
        val status = HttpStatusCode.fromValue(response.code)
        val contentType = response.header(HttpHeaders.ContentType)?.let { ContentType.parse(it) }
        try {
            call.respond(object : OutgoingContent.WriteChannelContent() {
                override val status = status
                override val contentType = contentType
                override val headers = io.ktor.http.Headers.build {
                    for (index in 0 until response.headers.size) {
                        val name = response.headers.name(index)
                        if (HostGateway.isHopByHop(name) || name.equals(HttpHeaders.ContentType, ignoreCase = true)) continue
                        append(name, response.headers.value(index))
                    }
                }
                override suspend fun writeTo(channel: ByteWriteChannel) {
                    val stream = response.body?.byteStream() ?: return
                    stream.use { input ->
                        val buffer = ByteArray(16 * 1024)
                        while (true) {
                            val read = withContext(Dispatchers.IO) { input.read(buffer) }
                            if (read <= 0) break
                            channel.writeFully(buffer, 0, read)
                        }
                    }
                }
            })
        } finally {
            response.close()
        }
    }

    private fun copyHeaders(call: ApplicationCall, builder: Request.Builder) {
        for (name in call.request.headers.names()) {
            if (HostGateway.isHopByHop(name)) continue
            if (name.equals("origin", true) || name.equals("referer", true) || name.equals("cookie", true) || name.equals("accept-encoding", true)) continue
            for (value in call.request.headers.getAll(name).orEmpty()) builder.addHeader(name, value)
        }
        val lan = lanOrigin().removePrefix("http://").removePrefix("https://")
        if (lan.isNotBlank()) {
            builder.header("X-Forwarded-Host", lan)
            builder.header("X-Forwarded-Proto", "http")
        }
    }
}
