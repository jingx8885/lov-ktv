package com.lovktv.tv

import android.content.res.AssetManager
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import io.ktor.http.HttpStatusCode
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
import io.ktor.server.response.respond
import io.ktor.server.response.respondText
import io.ktor.server.routing.get
import io.ktor.server.routing.route
import io.ktor.server.routing.routing
import io.ktor.server.websocket.WebSockets
import io.ktor.server.websocket.webSocket
import kotlinx.coroutines.CoroutineExceptionHandler
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/** Compatibility facade for the LAN host. Handlers own protocol-specific work. */
class HostServer(
    private val assets: AssetManager,
    processOrigin: String,
    private val cache: MediaCache,
    private val preferredPort: Int = HostRuntime.DEFAULT_PORT,
    private val assetRev: String = "",
    private val persistRoom: (String) -> Unit = {},
) {
    companion object {
        const val CORS_ALLOW_METHODS = "GET, POST, OPTIONS"
        const val CORS_ALLOW_HEADERS = "Content-Type, Accept, Accept-Language, X-LovKtv-Machine"
    }

    @Volatile var processOrigin: String = Prefs.normalize(processOrigin)
    val localRoom = LocalRoom { cache.getSong(it) }
    private val http = OkHttpClient.Builder().connectTimeout(12, TimeUnit.SECONDS).readTimeout(0, TimeUnit.SECONDS)
        .writeTimeout(0, TimeUnit.SECONDS).pingInterval(20, TimeUnit.SECONDS).followRedirects(true).followSslRedirects(true).build()
    private val apiHttp = OkHttpClient.Builder().connectTimeout(12, TimeUnit.SECONDS).readTimeout(20, TimeUnit.SECONDS)
        .writeTimeout(20, TimeUnit.SECONDS).followRedirects(true).followSslRedirects(true).build()
    private val webSockets = HostWebSocketHandler(localRoom, http) { this.processOrigin }
    val puller = SongPuller(cache, http, { this.processOrigin }) { songId ->
        localRoom.refreshSong(songId)
        val code = HostRuntime.roomCode.ifBlank { localRoom.activeCode() }
        if (code.isNotBlank()) webSockets.broadcastAsync(code, localRoom.snapshot(code).toJson())
    }
    private val api = HostApiHandler(cache, localRoom, puller, apiHttp, http,
        processOrigin = { this.processOrigin }, lanOrigin = { HostRuntime.lanOrigin },
        rememberCode = { rememberCode(it) }, broadcast = { code, json -> webSockets.broadcastAsync(code, json) })
    private val media = MediaRequestHandler(cache, apiHttp, { this.processOrigin }, puller::hint, api::proxyEmpty)
    private val assetsHandler = StaticAssetHandler(assets, assetRev)
    private val roomSync = Executors.newSingleThreadScheduledExecutor { runnable -> Thread(runnable, "lovktv-room").apply { isDaemon = true } }
    @Volatile private var lastPublishedLan = ""
    @Volatile private var lastPublishedAt = 0L
    private var engine: ApplicationEngine? = null

    fun start(): Int {
        val port = PortPicker.firstFree(preferredPort)
        val handler = CoroutineExceptionHandler { _, exc -> android.util.Log.e("HostServer", "ktor failed", exc) }
        val env = applicationEngineEnvironment {
            parentCoroutineContext = handler
            connector { host = "0.0.0.0"; this.port = port }
            module {
                install(WebSockets)
                routing {
                    get("/") { assetsHandler.serve(call, "/") }
                    webSocket("/ws/box/{code}") { webSockets.serveBox(this, call.parameters["code"].orEmpty()) }
                    webSocket("/ws/{path...}") { webSockets.proxy(this, call.request.path(), call.request.queryString()) }
                    route("{path...}") { handle { dispatch(call) } }
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
        puller.stop(); roomSync.shutdownNow(); webSockets.stop()
        engine?.stop(200, 800); engine = null
    }

    private fun rememberCode(code: String) {
        val next = Prefs.validRoom(code)
        if (next.isBlank()) return
        HostRuntime.roomCode = next; persistRoom(next)
    }

    private suspend fun dispatch(call: ApplicationCall) {
        allowPhone(call)
        if (call.request.httpMethod == HttpMethod.Options) { call.respond(HttpStatusCode.NoContent); return }
        val path = call.request.path().ifBlank { "/" }
        when (val kind = HostGateway.classify(path, call.request.httpMethod.value)) {
            ApiKind.Host -> respondHost(call)
            ApiKind.Static -> assetsHandler.serve(call, path)
            is ApiKind.Media -> media.serve(call, kind.songId, kind.name)
            else -> api.handle(call, kind)
        }
    }

    private suspend fun respondHost(call: ApplicationCall) {
        val info = HostGateway.hostPayload(HostRuntime.lanOrigin.ifBlank { LanAddress.origin(HostRuntime.port) }, processOrigin,
            HostRuntime.roomCode.ifBlank { localRoom.activeCode() }, cache.listReady().size, HostRuntime.micPort, LanMic.SAMPLE_RATE, assetRev)
        call.response.headers.append(HttpHeaders.CacheControl, "no-store")
        call.respondText(HostGateway.toJson(info), io.ktor.http.ContentType.Application.Json)
    }

    private fun syncProcessRoom() {
        var code = HostRuntime.roomCode.trim()
        if (code.isBlank()) { code = localRoom.activeCode(); if (code.isNotBlank()) HostRuntime.roomCode = code }
        val origin = processOrigin.trim().trimEnd('/')
        if (code.isBlank() || origin.isBlank()) return
        rememberCode(code); refreshLanOrigin(); publishLan(origin, code)
        try {
            val request = Request.Builder().url(HostGateway.remoteUrl(origin, "/api/rooms/$code", null)).header("Accept", "application/json").header("User-Agent", "LovKtv-TV/1.0").build()
            apiHttp.newCall(request).execute().use { response ->
                if (!response.isSuccessful) return
                val text = response.body?.string().orEmpty(); if (text.isBlank()) return
                val remote = JSONObject(text); val remoteQueue = remote.optJSONArray("queue")
                if (!RoomSync.shouldImportCloud(localRoom.snapshot(code).queue.size, remoteQueue?.length() ?: 0)) return
                localRoom.importSnapshot(text)
            }
        } catch (exc: Exception) { android.util.Log.w("HostServer", "syncProcessRoom $code failed: ${exc.message}") }
    }

    private fun refreshLanOrigin() {
        val port = HostRuntime.port
        if (port in 1..65535) HostRuntime.lanOrigin = LanAddress.origin(port)
    }

    private fun publishLan(process: String, code: String) {
        val lan = HostRuntime.lanOrigin.ifBlank { LanAddress.origin(HostRuntime.port) }; val now = System.currentTimeMillis()
        if (!LanDirectory.shouldPublish(lastPublishedLan, lan, lastPublishedAt, now)) return
        try {
            val body = LanDirectory.publishBody(lan, HostRuntime.micPort, LanMic.SAMPLE_RATE).toRequestBody("application/json; charset=utf-8".toMediaTypeOrNull())
            val request = Request.Builder().url(HostGateway.remoteUrl(process, "/api/rooms/$code/lan", null)).post(body).header("Accept", "application/json").header("User-Agent", "LovKtv-TV/1.0").build()
            apiHttp.newCall(request).execute().use { response -> if (response.isSuccessful) { lastPublishedLan = lan; lastPublishedAt = now } }
        } catch (exc: Exception) { android.util.Log.w("HostServer", "publishLan $code failed: ${exc.message}") }
    }

    private fun allowPhone(call: ApplicationCall) {
        call.response.headers.append("Access-Control-Allow-Origin", "*")
        call.response.headers.append("Access-Control-Allow-Methods", CORS_ALLOW_METHODS)
        call.response.headers.append("Access-Control-Allow-Headers", CORS_ALLOW_HEADERS)
    }
}
