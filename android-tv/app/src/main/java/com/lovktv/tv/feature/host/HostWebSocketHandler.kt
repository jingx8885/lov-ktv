package com.lovktv.tv.feature.host


import com.lovktv.tv.platform.Prefs
import com.lovktv.tv.room.LocalRoom
import io.ktor.server.websocket.DefaultWebSocketServerSession
import io.ktor.websocket.CloseReason
import io.ktor.websocket.Frame
import io.ktor.websocket.close
import io.ktor.websocket.readBytes
import io.ktor.websocket.readReason
import io.ktor.websocket.readText
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.channels.ClosedReceiveChannelException
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import okio.ByteString.Companion.toByteString
import org.json.JSONObject
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CopyOnWriteArraySet

/** Owns LAN room sockets and the transparent process WebSocket bridge. */
class HostWebSocketHandler(
    private val localRoom: LocalRoom,
    private val http: OkHttpClient,
    private val processOrigin: () -> String,
) {
    private val sockets = ConcurrentHashMap<String, CopyOnWriteArraySet<DefaultWebSocketServerSession>>()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    suspend fun serveBox(session: DefaultWebSocketServerSession, codeRaw: String) {
        val code = Prefs.validRoom(codeRaw)
        if (code.isBlank()) {
            session.close(CloseReason(CloseReason.Codes.CANNOT_ACCEPT, "room"))
            return
        }
        val peers = sockets.getOrPut(code) { CopyOnWriteArraySet() }
        peers.add(session)
        try {
            val snapshot = JSONObject().put("type", "snapshot").put("room", JSONObject(localRoom.snapshot(code).toJson()))
            session.outgoing.send(Frame.Text(snapshot.toString()))
            for (frame in session.incoming) if (frame is Frame.Close) break
        } catch (_: ClosedReceiveChannelException) {
        } finally {
            peers.remove(session)
            if (peers.isEmpty()) sockets.remove(code, peers)
        }
    }

    fun broadcastAsync(code: String, json: String) {
        val room = code.trim().uppercase()
        if (room.isBlank() || json.isBlank()) return
        scope.launch { broadcast(room, json) }
    }

    suspend fun proxy(session: DefaultWebSocketServerSession, path: String, query: String) {
        val remote = HostGateway.websocketUrl(HostGateway.remoteUrl(processOrigin(), path, query.ifBlank { null }))
        val remoteSocket = http.newWebSocket(Request.Builder().url(remote).build(), object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) {
                scope.launch { session.outgoing.send(Frame.Text(text)) }
            }
            override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                scope.launch { session.outgoing.send(Frame.Binary(true, bytes.toByteArray())) }
            }
            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                scope.launch { session.close(CloseReason(code.toShort(), reason)) }
            }
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: okhttp3.Response?) {
                scope.launch { session.close(CloseReason(CloseReason.Codes.INTERNAL_ERROR, t.message ?: "ws")) }
            }
        })
        try {
            for (frame in session.incoming) {
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

    fun stop() {
        scope.cancel()
        sockets.clear()
    }

    private suspend fun broadcast(code: String, json: String) {
        val peers = sockets[code] ?: return
        val payload = JSONObject().put("type", "snapshot").put("room", JSONObject(json)).toString()
        for (peer in peers) runCatching { peer.outgoing.send(Frame.Text(payload)) }
    }
}
