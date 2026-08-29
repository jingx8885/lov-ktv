package com.lovktv.tv

import org.json.JSONObject
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

class SongPuller(
    private val cache: MediaCache,
    private val http: OkHttpClient,
    private val processOrigin: () -> String,
    private val onSong: (String) -> Unit = {},
) {
    private val running = AtomicBoolean(false)
    private val executor = Executors.newSingleThreadScheduledExecutor { runnable ->
        Thread(runnable, "lovktv-cache").apply { isDaemon = true }
    }
    private var job: ScheduledFuture<*>? = null

    fun start(periodSec: Long = 12) {
        if (!running.compareAndSet(false, true)) return
        job = executor.scheduleWithFixedDelay({ runCatching { syncOnce() } }, 2, periodSec, TimeUnit.SECONDS)
    }

    fun hint() {
        executor.execute { runCatching { syncOnce() } }
    }

    fun stop() {
        running.set(false)
        job?.cancel(false)
        job = null
    }

    fun syncOnce() {
        val origin = processOrigin().trim().trimEnd('/')
        if (origin.isBlank()) return
        val list = getJson(HostGateway.remoteUrl(origin, "/api/songs", null)) ?: return
        val songs = list.optJSONArray("songs") ?: return
        for (i in 0 until songs.length()) {
            val row = songs.optJSONObject(i) ?: continue
            if (row.optString("status") != "ready") continue
            pullSong(origin, row.optString("id"), row)
        }
    }

    fun pullSong(origin: String, songId: String, seed: JSONObject? = null) {
        if (!MediaCache.safeId(songId)) return
        val detail = getJson(HostGateway.remoteUrl(origin, "/api/songs/$songId", null)) ?: seed ?: return
        val remoteFiles = buildList {
            val files = detail.optJSONArray("files")
            if (files != null) {
                for (i in 0 until files.length()) add(files.optString(i))
            }
        }
        val remoteRev = detail.optString("media_rev")
        val cached = cache.getSong(songId)
        val wasSingable = cached?.singable == true
        val stale = remoteRev.isNotBlank() && cached?.mediaRev != remoteRev
        val wanted = MediaCache.wantedFiles(remoteFiles).ifEmpty { MediaCache.WANTED }
        var complete = true
        for (name in wanted) {
            val dest = cache.file(songId, name)
            if (dest == null) {
                complete = false
                continue
            }
            val have = dest.exists() && dest.length() > 0
            if (!(have && ((remoteRev.isNotBlank() && !stale) || (remoteRev.isBlank() && name != "lyrics.json")))) {
                download(origin, songId, name, remoteRev)
            }
            if (!dest.exists() || dest.length() <= 0) complete = false
        }
        cache.writeMeta(
            mapOf(
                "id" to songId,
                "title" to detail.optString("title", seed?.optString("title").orEmpty()),
                "artist" to detail.optString("artist", seed?.optString("artist").orEmpty()),
                "language" to detail.optString("language", seed?.optString("language", "zh").orEmpty()),
                "status" to "ready",
                "media_rev" to if (complete) remoteRev else cached?.mediaRev.orEmpty(),
            ),
            wanted,
        )
        if (complete && !wasSingable) onSong(songId)
    }

    private fun download(origin: String, songId: String, name: String, rev: String) {
        val query = if (rev.isNotBlank()) "v=$rev" else null
        val url = HostGateway.remoteUrl(origin, "/media/$songId/$name", query)
        val request = Request.Builder().url(url).build()
        http.newCall(request).execute().use { response ->
            if (!response.isSuccessful) return
            val bytes = response.body?.bytes() ?: return
            if (bytes.isEmpty()) return
            cache.putFile(songId, name, bytes)
        }
    }

    private fun getJson(url: String): JSONObject? {
        val request = Request.Builder().url(url).build()
        return http.newCall(request).execute().use { response ->
            if (!response.isSuccessful) return null
            val text = response.body?.string().orEmpty()
            if (text.isBlank()) null else JSONObject(text)
        }
    }
}
