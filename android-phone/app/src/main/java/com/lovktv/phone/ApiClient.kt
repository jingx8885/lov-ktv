package com.lovktv.phone

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class ApiException(message: String) : Exception(message)

class ApiClient(base: String) {
    private val root = base.trim().trimEnd('/')
    private val http = OkHttpClient.Builder()
        .connectTimeout(8, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .build()

    fun host(): HostInfo = HostParser.parse(get("/api/host"))

    fun room(code: String): RoomView = Models.room(get("/api/rooms/${code.uppercase()}"))

    fun search(query: String, page: Int = 1): List<SearchHit> {
        val path = "/api/search?q=${java.net.URLEncoder.encode(query, "UTF-8")}&page=$page&count=10"
        return Models.hits(get(path))
    }

    fun songs(): List<SongRow> = Models.songs(get("/api/songs"))

    fun importHit(query: String, hit: SearchHit): String {
        val body = JSONObject()
            .put("query", query)
            .put("id", hit.id)
            .put("title", hit.title)
            .put("artist", hit.artist)
            .put("language", hit.language)
            .put("source", hit.source)
        return Models.importedId(post("/api/songs/import", body))
    }

    fun queue(code: String, songId: String): RoomView {
        val body = JSONObject().put("song_id", songId)
        return Models.room(post("/api/rooms/${code.uppercase()}/queue", body))
    }

    private fun get(path: String): String = execute(
        Request.Builder().url(url(path)).get().build(),
    )

    private fun post(path: String, body: JSONObject): String = execute(
        Request.Builder()
            .url(url(path))
            .post(body.toString().toRequestBody(JSON))
            .build(),
    )

    private fun url(path: String): String {
        return if (path.startsWith("http")) path else root + if (path.startsWith("/")) path else "/$path"
    }

    private fun execute(request: Request): String {
        http.newCall(request).execute().use { response ->
            val text = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw ApiException(Models.errorDetail(text, "请求失败 ${response.code}"))
            }
            return text
        }
    }

    companion object {
        private val JSON = "application/json; charset=utf-8".toMediaType()
    }
}
