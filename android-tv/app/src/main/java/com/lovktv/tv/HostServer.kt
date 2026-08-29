package com.lovktv.tv

import android.content.res.AssetManager
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.withCharset
import io.ktor.http.content.OutgoingContent
import io.ktor.server.application.ApplicationCall
import io.ktor.server.application.call
import io.ktor.server.application.install
import io.ktor.server.cio.CIO
import io.ktor.server.engine.ApplicationEngine
import io.ktor.server.engine.applicationEngineEnvironment
import io.ktor.server.engine.connector
import io.ktor.server.engine.embeddedServer
import io.ktor.server.request.httpMethod
import io.ktor.server.request.path
import io.ktor.server.request.queryString
import io.ktor.server.request.receive
import io.ktor.server.response.respond
import io.ktor.server.response.respondBytes
import io.ktor.server.response.respondText
import io.ktor.server.routing.get
import io.ktor.server.routing.route
import io.ktor.server.routing.routing
import io.ktor.server.websocket.DefaultWebSocketServerSession
import io.ktor.server.websocket.WebSockets
import io.ktor.server.websocket.webSocket
import io.ktor.utils.io.ByteWriteChannel
import io.ktor.utils.io.writeFully
import io.ktor.websocket.CloseReason
import io.ktor.websocket.Frame
import io.ktor.websocket.close
import io.ktor.websocket.readBytes
import io.ktor.websocket.readReason
import io.ktor.websocket.readText
import kotlinx.coroutines.CoroutineExceptionHandler
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.ClosedReceiveChannelException
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import okio.ByteString.Companion.toByteString
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

class HostServer(
    private val assets: AssetManager,
    processOrigin: String,
    private val cache: MediaCache,
    private val preferredPort: Int = HostRuntime.DEFAULT_PORT,
    private val assetRev: String = "",
    private val persistRoom: (String) -> Unit = {},
) {
    @Volatile
    var processOrigin: String = Prefs.normalize(processOrigin)

    val localRoom = LocalRoom { cache.getSong(it) }

    private val http = OkHttpClient.Builder()
        .connectTimeout(12, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.SECONDS)
        .writeTimeout(0, TimeUnit.SECONDS)
        .pingInterval(20, TimeUnit.SECONDS)
        .followRedirects(true)
        .followSslRedirects(true)
        .build()

    private val apiHttp = OkHttpClient.Builder()
        .connectTimeout(12, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .writeTimeout(20, TimeUnit.SECONDS)
        .followRedirects(true)
        .followSslRedirects(true)
        .build()

    val puller = SongPuller(cache, http) { this.processOrigin }

    private val roomSync = Executors.newSingleThreadScheduledExecutor { runnable ->
        Thread(runnable, "lovktv-room").apply { isDaemon = true }
    }

    private var engine: ApplicationEngine? = null

    fun start(): Int {
        val port = PortPicker.firstFree(preferredPort)
        val handler = CoroutineExceptionHandler { _, exc ->
            android.util.Log.e("HostServer", "ktor failed", exc)
        }
        val env = applicationEngineEnvironment {
            parentCoroutineContext = handler
            connector {
                this.host = "0.0.0.0"
                this.port = port
            }
            module {
                install(WebSockets)
                routing {
                    get("/") { serveAsset(call, "/") }
                    webSocket("/ws/{path...}") {
                        proxyWebSocket(call.request.path(), call.request.queryString())
                    }
                    route("{path...}") {
                        handle { dispatch(call) }
                    }
                }
            }
        }
        val server = embeddedServer(CIO, environment = env)
        server.start(wait = false)
        engine = server
        HostRuntime.port = port
        HostRuntime.processOrigin = processOrigin
        HostRuntime.lanOrigin = LanAddress.origin(port)
        HostRuntime.ready = true
        if (HostRuntime.roomCode.isNotBlank()) localRoom.ensure(HostRuntime.roomCode)
        puller.start()
        roomSync.scheduleWithFixedDelay({ runCatching { syncProcessRoom() } }, 1, 2, TimeUnit.SECONDS)
        return port
    }

    fun stop() {
        HostRuntime.ready = false
        puller.stop()
        roomSync.shutdownNow()
        engine?.stop(200, 800)
        engine = null
    }

    private fun rememberCode(code: String) {
        val next = Prefs.validRoom(code)
        if (next.isBlank()) return
        HostRuntime.roomCode = next
        persistRoom(next)
    }

    private fun syncProcessRoom() {
        var code = HostRuntime.roomCode.trim()
        if (code.isBlank()) {
            code = localRoom.activeCode()
            if (code.isNotBlank()) HostRuntime.roomCode = code
        }
        val origin = processOrigin.trim().trimEnd('/')
        if (code.isBlank() || origin.isBlank()) return
        try {
            val request = Request.Builder()
                .url(HostGateway.remoteUrl(origin, "/api/rooms/$code", null))
                .header("Accept", "application/json")
                .header("User-Agent", "LovKtv-TV/1.0")
                .build()
            apiHttp.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    android.util.Log.w("HostServer", "syncProcessRoom $code -> ${response.code}")
                    return
                }
                val text = response.body?.string().orEmpty()
                if (text.isBlank()) return
                val remote = JSONObject(text)
                val remoteQueue = remote.optJSONArray("queue")
                val remoteHas = remoteQueue != null && remoteQueue.length() > 0
                val local = localRoom.snapshot(code)
                if (!RoomSync.shouldImportCloud(local.queue.size, if (remoteHas) remoteQueue!!.length() else 0)) {
                    rememberCode(code)
                    return
                }
                localRoom.importSnapshot(text)
                rememberCode(code)
            }
        } catch (exc: Exception) {
            android.util.Log.w("HostServer", "syncProcessRoom $code failed: ${exc.message}")
        }
    }

    private suspend fun dispatch(call: ApplicationCall) {
        val path = call.request.path().ifBlank { "/" }
        val method = call.request.httpMethod.value
        when (val kind = HostGateway.classify(path, method)) {
            ApiKind.Host -> respondHost(call)
            ApiKind.Static -> serveAsset(call, path)
            is ApiKind.Media -> serveMedia(call, kind.songId, kind.name)
            else -> proxyOrFallback(call, kind)
        }
    }

    private suspend fun respondHost(call: ApplicationCall) {
        val info = HostGateway.hostPayload(
            lanOrigin = HostRuntime.lanOrigin.ifBlank { LanAddress.origin(HostRuntime.port) },
            processOrigin = processOrigin,
            room = HostRuntime.roomCode.ifBlank { localRoom.activeCode() },
            cacheReady = cache.listReady().size,
            micPort = HostRuntime.micPort,
            micSampleRate = LanMic.SAMPLE_RATE,
        )
        call.response.headers.append(HttpHeaders.CacheControl, "no-store")
        call.respondText(HostGateway.toJson(info), ContentType.Application.Json)
    }

    private suspend fun serveMedia(call: ApplicationCall, songId: String, name: String) {
        val local = cache.file(songId, name)
        if (local != null && local.exists() && local.length() > 0) {
            serveFile(call, local)
            return
        }
        puller.hint()
        if (shouldCacheMedia(name)) {
            val bytes = withContext(Dispatchers.IO) { fetchMediaBytes(songId, name) }
            if (bytes != null && bytes.isNotEmpty()) {
                cache.putFile(songId, name, bytes)
                call.response.headers.append(HttpHeaders.CacheControl, "no-cache, must-revalidate")
                call.response.headers.append("Access-Control-Allow-Origin", "*")
                call.respondBytes(bytes, mime(name))
                return
            }
        }
        proxyHttp(call, ByteArray(0))
    }

    private fun shouldCacheMedia(name: String): Boolean {
        return name.endsWith(".json") || name == "cover.jpg"
    }

    private fun fetchMediaBytes(songId: String, name: String): ByteArray? {
        return try {
            val remote = HostGateway.remoteUrl(processOrigin, "/media/$songId/$name", null)
            val request = Request.Builder()
                .url(remote)
                .header("Accept", "*/*")
                .header("User-Agent", "LovKtv-TV/1.0")
                .build()
            apiHttp.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    android.util.Log.w("HostServer", "fetchMedia $songId/$name -> ${response.code}")
                    return null
                }
                val bytes = response.body?.bytes() ?: return null
                if (bytes.size > 2_000_000) return null
                bytes
            }
        } catch (exc: Exception) {
            android.util.Log.w("HostServer", "fetchMedia $songId/$name failed: ${exc.message}")
            null
        }
    }

    private suspend fun proxyOrFallback(call: ApplicationCall, kind: ApiKind) {
        val method = call.request.httpMethod.value
        val incoming = if (method == "GET" || method == "HEAD") {
            ByteArray(0)
        } else {
            call.receive<ByteArray>()
        }
        val localRoomApi = kind is ApiKind.RoomCreate || kind is ApiKind.RoomGet ||
            kind is ApiKind.RoomQueue || kind is ApiKind.RoomBump ||
            kind is ApiKind.RoomSkip || kind is ApiKind.RoomPlay || kind is ApiKind.RoomMix
        if (localRoomApi) {
            try {
                val json = fallbackJson(kind, incoming)
                runCatching { rememberCode(JSONObject(json).optString("code")) }
                call.response.headers.append(HttpHeaders.CacheControl, "no-store")
                call.response.headers.append("Access-Control-Allow-Origin", "*")
                call.respondText(json, ContentType.Application.Json)
                if (kind is ApiKind.RoomQueue || kind is ApiKind.RoomPlay) puller.hint()
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

    private fun rememberRemote(kind: ApiKind, body: ByteArray) {
        val text = body.toString(Charsets.UTF_8)
        if (text.isBlank()) return
        when (kind) {
            is ApiKind.RoomGet, is ApiKind.RoomQueue, is ApiKind.RoomBump,
            is ApiKind.RoomSkip, is ApiKind.RoomPlay, is ApiKind.RoomMix,
            ApiKind.RoomCreate,
            -> {
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
            ).toJson()
            else -> throw IllegalArgumentException("处理服务器暂时连不上")
        }
    }

    private fun fetchApi(call: ApplicationCall, incoming: ByteArray): ByteArray? {
        return try {
            val remote = HostGateway.remoteUrl(
                processOrigin,
                call.request.path(),
                call.request.queryString().ifBlank { null },
            )
            val method = call.request.httpMethod.value
            val mediaType = "application/json; charset=utf-8".toMediaTypeOrNull()
            val body: RequestBody? = if (method == "GET" || method == "HEAD") null else incoming.toRequestBody(mediaType)
            val builder = Request.Builder()
                .url(remote)
                .method(method, body)
                .header("Accept", "application/json")
                .header("User-Agent", "LovKtv-TV/1.0")
            apiHttp.newCall(builder.build()).execute().use { response ->
                if (!response.isSuccessful) {
                    android.util.Log.w("HostServer", "fetchApi ${call.request.path()} -> ${response.code}")
                    return null
                }
                response.body?.bytes()
            }
        } catch (exc: Exception) {
            android.util.Log.w("HostServer", "fetchApi ${call.request.path()} failed: ${exc.message}")
            null
        }
    }

    private suspend fun serveFile(call: ApplicationCall, file: File) {
        val size = file.length()
        val range = MediaCache.parseRange(call.request.headers[HttpHeaders.Range], size)
        val type = mime(file.name)
        call.response.headers.append(HttpHeaders.AcceptRanges, "bytes")
        call.response.headers.append(HttpHeaders.CacheControl, "no-cache, must-revalidate")
        call.response.headers.append("Access-Control-Allow-Origin", "*")
        if (range == null) {
            call.respond(object : OutgoingContent.WriteChannelContent() {
                override val status = HttpStatusCode.OK
                override val contentType = type
                override val contentLength = size
                override suspend fun writeTo(channel: ByteWriteChannel) {
                    file.inputStream().use { input ->
                        val buffer = ByteArray(16 * 1024)
                        while (true) {
                            val read = withContext(Dispatchers.IO) { input.read(buffer) }
                            if (read <= 0) break
                            channel.writeFully(buffer, 0, read)
                        }
                    }
                }
            })
            return
        }
        val (start, end) = range
        val length = end - start + 1
        call.respond(object : OutgoingContent.WriteChannelContent() {
            override val status = HttpStatusCode.PartialContent
            override val contentType = type
            override val contentLength = length
            override val headers = io.ktor.http.Headers.build {
                append(HttpHeaders.ContentRange, "bytes $start-$end/$size")
                append(HttpHeaders.AcceptRanges, "bytes")
            }
            override suspend fun writeTo(channel: ByteWriteChannel) {
                file.inputStream().use { input ->
                    withContext(Dispatchers.IO) { input.skip(start) }
                    var left = length
                    val buffer = ByteArray(16 * 1024)
                    while (left > 0) {
                        val read = withContext(Dispatchers.IO) {
                            input.read(buffer, 0, minOf(buffer.size.toLong(), left).toInt())
                        }
                        if (read <= 0) break
                        channel.writeFully(buffer, 0, read)
                        left -= read
                    }
                }
            }
        })
    }

    private suspend fun serveAsset(call: ApplicationCall, path: String) {
        val name = assetName(path)
        val bytes = withContext(Dispatchers.IO) { readAsset(name) }
        if (bytes == null) {
            call.respond(HttpStatusCode.NotFound, "not found")
            return
        }
        val body = if (AssetRev.shouldRewrite(name) && assetRev.isNotBlank()) {
            AssetRev.rewrite(String(bytes, Charsets.UTF_8), assetRev).toByteArray(Charsets.UTF_8)
        } else {
            bytes
        }
        if (name.endsWith(".html")) {
            call.response.headers.append(HttpHeaders.CacheControl, "no-store, max-age=0")
            call.response.headers.append("Pragma", "no-cache")
        } else if (AssetRev.shouldRewrite(name) && assetRev.isNotBlank()) {
            call.response.headers.append(HttpHeaders.CacheControl, "public, max-age=31536000, immutable")
        }
        call.respondBytes(body, contentType = mime(name))
    }

    private suspend fun proxyHttp(call: ApplicationCall, incoming: ByteArray) {
        val remote = HostGateway.remoteUrl(
            processOrigin,
            call.request.path(),
            call.request.queryString().ifBlank { null },
        )
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
                override val status: HttpStatusCode = status
                override val contentType: ContentType? = contentType
                override val headers = io.ktor.http.Headers.build {
                    for (index in 0 until response.headers.size) {
                        val name = response.headers.name(index)
                        if (HostGateway.isHopByHop(name) || name.equals(HttpHeaders.ContentType, ignoreCase = true)) {
                            continue
                        }
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
            if (name.equals("origin", ignoreCase = true) ||
                name.equals("referer", ignoreCase = true) ||
                name.equals("cookie", ignoreCase = true) ||
                name.equals("accept-encoding", ignoreCase = true)
            ) {
                continue
            }
            for (value in call.request.headers.getAll(name).orEmpty()) {
                builder.addHeader(name, value)
            }
        }
        val lan = HostRuntime.lanOrigin.removePrefix("http://").removePrefix("https://")
        if (lan.isNotBlank()) {
            builder.header("X-Forwarded-Host", lan)
            builder.header("X-Forwarded-Proto", "http")
        }
    }

    private suspend fun DefaultWebSocketServerSession.proxyWebSocket(path: String, query: String) {
        val remote = HostGateway.websocketUrl(
            HostGateway.remoteUrl(processOrigin, path, query.ifBlank { null }),
        )
        val request = Request.Builder().url(remote).build()
        val remoteSocket = http.newWebSocket(
            request,
            object : WebSocketListener() {
                override fun onMessage(webSocket: WebSocket, text: String) {
                    launch { outgoing.send(Frame.Text(text)) }
                }

                override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                    launch { outgoing.send(Frame.Binary(true, bytes.toByteArray())) }
                }

                override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                    launch { close(CloseReason(code.toShort(), reason)) }
                }

                override fun onFailure(webSocket: WebSocket, t: Throwable, response: okhttp3.Response?) {
                    launch { close(CloseReason(CloseReason.Codes.INTERNAL_ERROR, t.message ?: "ws")) }
                }
            },
        )
        try {
            for (frame in incoming) {
                when (frame) {
                    is Frame.Text -> remoteSocket.send(frame.readText())
                    is Frame.Binary -> remoteSocket.send(frame.readBytes().toByteString())
                    is Frame.Close -> {
                        val reason = frame.readReason()
                        remoteSocket.close(reason?.code?.toInt() ?: 1000, reason?.message.orEmpty())
                    }
                    else -> Unit
                }
            }
        } catch (_: ClosedReceiveChannelException) {
        } finally {
            remoteSocket.close(1000, "bye")
        }
    }

    private fun readAsset(name: String): ByteArray? {
        return try {
            assets.open(name).use { it.readBytes() }
        } catch (_: IOException) {
            null
        }
    }

    private fun assetName(path: String): String {
        val clean = path.substringBefore('?').trimStart('/')
        val relative = if (clean.isEmpty() || clean.endsWith("/")) {
            clean + "index.html"
        } else {
            clean
        }
        return "web/$relative"
    }

    private fun mime(name: String): ContentType {
        return when {
            name.endsWith(".html") -> ContentType.Text.Html.withCharset(Charsets.UTF_8)
            name.endsWith(".css") -> ContentType.Text.CSS.withCharset(Charsets.UTF_8)
            name.endsWith(".js") -> ContentType.Application.JavaScript.withCharset(Charsets.UTF_8)
            name.endsWith(".json") -> ContentType.Application.Json
            name.endsWith(".svg") -> ContentType.parse("image/svg+xml")
            name.endsWith(".png") -> ContentType.Image.PNG
            name.endsWith(".jpg") || name.endsWith(".jpeg") -> ContentType.Image.JPEG
            name.endsWith(".m4a") -> ContentType.parse("audio/mp4")
            name.endsWith(".mp3") -> ContentType.parse("audio/mpeg")
            name.endsWith(".mp4") -> ContentType.parse("video/mp4")
            else -> ContentType.Application.OctetStream
        }
    }
}
