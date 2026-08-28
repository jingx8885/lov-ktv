package com.lovktv.phone

import org.json.JSONArray
import org.json.JSONObject

data class SongRow(
    val id: String,
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
    val queue: List<SongRow>,
)

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

    private fun song(item: JSONObject): SongRow {
        return SongRow(
            id = item.optString("id").ifBlank { item.optString("song_id") },
            title = item.optString("title"),
            artist = item.optString("artist"),
            status = item.optString("status"),
            language = item.optString("language"),
        )
    }
}
