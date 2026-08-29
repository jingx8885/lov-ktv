package com.lovktv.tv.room

import com.lovktv.tv.media.CachedSong

import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID
import kotlin.math.max
import kotlin.math.min

data class QueueItem(
    val id: String,
    val songId: String,
    val position: Int,
    val title: String,
    val artist: String,
    val status: String,
    val language: String,
    val mediaRev: String = "",
) {
    fun toJson(): JSONObject {
        return JSONObject()
            .put("id", id)
            .put("song_id", songId)
            .put("position", position)
            .put("title", title)
            .put("artist", artist)
            .put("status", status)
            .put("language", language)
            .put("media_rev", mediaRev)
    }
}

data class RoomSnap(
    val code: String,
    val vocalMix: Double = 1.0,
    val volume: Int = 80,
    val micGain: Int = 80,
    val nowIndex: Int = 0,
    val paused: Boolean = false,
    val queue: List<QueueItem> = emptyList(),
) {
    val nowPlaying: QueueItem?
        get() = queue.getOrNull(nowIndex)

    fun toJson(): String {
        val now = nowPlaying
        return JSONObject()
            .put("code", code)
            .put("vocal_mix", vocalMix)
            .put("volume", volume)
            .put("mic_gain", micGain)
            .put("now_index", nowIndex)
            .put("paused", paused)
            .put("queue", JSONArray(queue.map { it.toJson() }))
            .put("now_playing", now?.toJson() ?: JSONObject.NULL)
            .put("mic_on", false)
            .put("mic_peer", "")
            .put("source", "cache")
            .toString()
    }
}

class LocalRoom(
    private val songLookup: (String) -> CachedSong?,
) {
    private val rooms = LinkedHashMap<String, RoomSnap>()

    @Synchronized
    fun ensure(code: String?): RoomSnap {
        val wanted = code?.trim()?.uppercase().orEmpty()
        val key = when {
            wanted.isNotBlank() -> wanted
            rooms.isNotEmpty() -> rooms.keys.last()
            else -> newCode()
        }
        return rooms.getOrPut(key) { RoomSnap(code = key) }
    }

    @Synchronized
    fun snapshot(code: String): RoomSnap {
        val room = ensure(code)
        val next = room.copy(queue = room.queue.map(::refreshItem))
        rooms[room.code] = next
        return next
    }

    @Synchronized
    fun activeCode(): String = rooms.keys.lastOrNull().orEmpty()

    @Synchronized
    fun enqueue(code: String, songId: String): RoomSnap {
        val room = ensure(code)
        val id = songId.trim()
        if (id.isBlank()) throw IllegalArgumentException("缺歌曲")
        val song = songLookup(id)
        if (room.queue.any { it.songId == id }) return snapshot(room.code)
        val item = QueueItem(
            id = newId(),
            songId = song?.id ?: id,
            position = (room.queue.maxOfOrNull { it.position } ?: 0) + 1,
            title = song?.title?.ifBlank { id } ?: id,
            artist = song?.artist.orEmpty(),
            status = itemStatus(song),
            language = song?.language ?: "zh",
            mediaRev = song?.mediaRev.orEmpty(),
        )
        val queue = room.queue + item
        val playing = room.nowPlaying != null
        val next = room.copy(queue = queue, nowIndex = if (playing) room.nowIndex else queue.lastIndex)
        rooms[room.code] = next
        return snapshot(room.code)
    }

    @Synchronized
    fun refreshSong(songId: String) {
        val id = songId.trim()
        if (id.isBlank()) return
        rooms.keys.toList().forEach { code ->
            val room = rooms[code] ?: return@forEach
            if (room.queue.none { it.songId == id }) return@forEach
            rooms[code] = room.copy(queue = room.queue.map { if (it.songId == id) refreshItem(it) else it })
        }
    }

    @Synchronized
    fun skip(code: String): RoomSnap {
        val room = ensure(code)
        if (room.queue.isEmpty() || room.nowPlaying == null) return room
        val cur = max(0, min(room.nowIndex, room.queue.lastIndex))
        val queue = room.queue.filterIndexed { index, _ -> index != cur }
        val nxt = when {
            queue.isEmpty() -> 0
            cur >= queue.size -> 0
            else -> cur
        }
        val next = room.copy(queue = queue, nowIndex = nxt, paused = false)
        rooms[room.code] = next
        return next
    }

    @Synchronized
    fun playNow(code: String, itemId: String = "", songId: String = ""): RoomSnap {
        var room = ensure(code)
        var id = itemId
        if (id.isBlank() && songId.isNotBlank()) {
            if (room.nowPlaying != null) {
                return enqueue(code, songId)
            }
            if (room.queue.none { it.songId == songId }) {
                room = enqueue(code, songId)
            }
            id = room.queue.firstOrNull { it.songId == songId }?.id.orEmpty()
        }
        val idx = room.queue.indexOfFirst { it.id == id }
        if (idx < 0) return room
        val next = room.copy(nowIndex = idx, paused = false)
        rooms[room.code] = next
        return next
    }

    @Synchronized
    fun bump(code: String, itemId: String): RoomSnap {
        val room = ensure(code)
        val idx = room.queue.indexOfFirst { it.id == itemId }
        if (idx < 0 || idx <= room.nowIndex + 1) return room
        val items = room.queue.toMutableList()
        val item = items.removeAt(idx)
        items.add(room.nowIndex + 1, item)
        val next = room.copy(queue = items)
        rooms[room.code] = next
        return next
    }

    @Synchronized
    fun setMix(code: String, vocalMix: Double? = null, volume: Int? = null, micGain: Int? = null, paused: Boolean? = null): RoomSnap {
        val room = ensure(code)
        val next = room.copy(
            vocalMix = vocalMix?.let { max(0.0, min(1.0, it)) } ?: room.vocalMix,
            volume = volume?.let { max(0, min(100, it)) } ?: room.volume,
            micGain = micGain?.let { max(0, min(100, it)) } ?: room.micGain,
            paused = paused ?: room.paused,
        )
        rooms[room.code] = next
        return next
    }

    @Synchronized
    fun importSnapshot(json: String): RoomSnap {
        val obj = JSONObject(json)
        val code = obj.optString("code").uppercase()
        val queue = jsonQueue(obj.optJSONArray("queue"))
        val nowId = obj.optJSONObject("now_playing")?.optString("id").orEmpty()
        val nowIndex = queue.indexOfFirst { it.id == nowId }.takeIf { it >= 0 }
            ?: obj.optInt("now_index", 0).coerceAtLeast(0)
        val snap = RoomSnap(
            code = code,
            vocalMix = obj.optDouble("vocal_mix", 1.0),
            volume = obj.optInt("volume", 80),
            micGain = obj.optInt("mic_gain", 80),
            nowIndex = if (queue.isEmpty()) 0 else nowIndex.coerceAtMost(queue.lastIndex),
            paused = jsonFlag(obj, "paused") ?: false,
            queue = queue,
        )
        rooms[code] = snap
        return snap
    }

    private fun itemStatus(song: CachedSong?): String {
        return when {
            song == null -> "fetching"
            song.singable -> "ready"
            else -> song.status.ifBlank { "fetching" }
        }
    }

    private fun refreshItem(item: QueueItem): QueueItem {
        val song = songLookup(item.songId)
        return item.copy(
            title = song?.title?.ifBlank { item.title } ?: item.title,
            artist = song?.artist?.ifBlank { item.artist } ?: item.artist,
            language = song?.language?.ifBlank { item.language } ?: item.language,
            status = itemStatus(song),
            mediaRev = song?.mediaRev?.ifBlank { item.mediaRev } ?: item.mediaRev,
        )
    }

    private fun jsonFlag(obj: JSONObject, key: String): Boolean? {
        if (!obj.has(key) || obj.isNull(key)) return null
        return when (val raw = obj.get(key)) {
            is Boolean -> raw
            is Number -> raw.toInt() != 0
            else -> obj.optBoolean(key)
        }
    }

    private fun jsonQueue(array: JSONArray?): List<QueueItem> {
        if (array == null) return emptyList()
        return buildList {
            for (i in 0 until array.length()) {
                val item = array.optJSONObject(i) ?: continue
                add(
                    QueueItem(
                        id = item.optString("id").ifBlank { newId() },
                        songId = item.optString("song_id"),
                        position = item.optInt("position", i + 1),
                        title = item.optString("title"),
                        artist = item.optString("artist"),
                        status = item.optString("status", "ready"),
                        language = item.optString("language", "zh"),
                        mediaRev = item.optString("media_rev").ifBlank {
                            songLookup(item.optString("song_id"))?.mediaRev.orEmpty()
                        },
                    ),
                )
            }
        }
    }

    private fun newId(): String = UUID.randomUUID().toString().replace("-", "").take(12)

    private fun newCode(): String = UUID.randomUUID().toString().replace("-", "").take(6).uppercase()
}
