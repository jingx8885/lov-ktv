package com.lovktv.phone

import org.json.JSONArray
import org.json.JSONObject

data class SongRow(
    val id: String,
    val songId: String,
    val title: String,
    val artist: String,
    val status: String,
    val language: String = "",
) {
    val ready: Boolean get() = status == "ready"
}

data class SearchHit(
    val id: String,
    val title: String,
    val artist: String,
    val language: String,
    val source: String,
    val isMv: Boolean,
)

data class RoomView(
    val code: String,
    val nowTitle: String,
    val nowArtist: String,
    val vocalMix: Double,
    val volume: Int,
    val nowIndex: Int,
    val queue: List<SongRow>,
) {
    val vocalOn: Boolean get() = vocalMix >= 0.5
}

object Models {
    fun songs(json: String): List<SongRow> {
        val root = JSONObject(json)
        val list = root.optJSONArray("songs") ?: JSONArray()
        return (0 until list.length()).map { index -> song(list.getJSONObject(index)) }
    }

    fun hits(json: String): List<SearchHit> {
        val root = JSONObject(json)
        val list = root.optJSONArray("hits") ?: JSONArray()
        return (0 until list.length()).map { index ->
            val item = list.getJSONObject(index)
            SearchHit(
                id = item.optString("id"),
                title = item.optString("title"),
                artist = item.optString("artist"),
                language = item.optString("language"),
                source = item.optString("source"),
                isMv = item.optBoolean("is_mv") || item.optString("source") == "mugen",
            )
        }
    }

    fun room(json: String): RoomView {
        val root = JSONObject(json)
        val now = root.optJSONObject("now_playing")
        val list = root.optJSONArray("queue") ?: JSONArray()
        return RoomView(
            code = root.optString("code").uppercase(),
            nowTitle = now?.optString("title").orEmpty(),
            nowArtist = now?.optString("artist").orEmpty(),
            vocalMix = root.optDouble("vocal_mix", 1.0),
            volume = root.optInt("volume", 80).coerceIn(0, 100),
            nowIndex = root.optInt("now_index", 0).coerceAtLeast(0),
            queue = (0 until list.length()).map { index -> song(list.getJSONObject(index)) },
        )
    }

    fun importedId(json: String): String {
        return JSONObject(json).optString("id")
    }

    fun errorDetail(json: String, fallback: String): String {
        return try {
            JSONObject(json).optString("detail").ifBlank { fallback }
        } catch (_: Exception) {
            fallback
        }
    }

    fun canBump(index: Int, nowIndex: Int): Boolean = index > nowIndex + 1

    private fun song(item: JSONObject): SongRow {
        val songId = item.optString("song_id").ifBlank { item.optString("id") }
        val id = item.optString("id").ifBlank { songId }
        return SongRow(
            id = id,
            songId = songId,
            title = item.optString("title"),
            artist = item.optString("artist"),
            status = item.optString("status"),
            language = item.optString("language"),
        )
    }
}
