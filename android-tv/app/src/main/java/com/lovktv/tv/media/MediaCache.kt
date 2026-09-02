package com.lovktv.tv.media


import org.json.JSONArray
import org.json.JSONObject
import java.io.File

data class CachedSong(
    val id: String,
    val title: String,
    val artist: String,
    val language: String,
    val status: String,
    val files: List<String>,
    val singable: Boolean,
    val mediaRev: String = "",
) {
    fun toJson(): JSONObject {
        return JSONObject()
            .put("id", id)
            .put("title", title)
            .put("artist", artist)
            .put("language", language)
            .put("status", if (singable) "ready" else status)
            .put("error", "")
            .put("files", JSONArray(files))
            .put("cached", true)
            .put("media_rev", mediaRev)
    }
}

class MediaCache(private val root: File) {
    init {
        root.mkdirs()
    }

    fun file(songId: String, name: String): File? {
        if (!safeId(songId) || !safeName(name)) return null
        return File(File(root, songId), name)
    }

    fun writeSong(meta: Map<String, String>, files: Map<String, ByteArray>) {
        val id = meta["id"] ?: return
        if (!safeId(id)) return
        val dir = File(root, id)
        dir.mkdirs()
        files.forEach { (name, bytes) ->
            if (safeName(name)) File(dir, name).writeBytes(bytes)
        }
        writeMeta(meta, files.keys.sorted())
    }

    fun putFile(songId: String, name: String, bytes: ByteArray): File? {
        val dest = file(songId, name) ?: return null
        dest.parentFile?.mkdirs()
        val part = File(dest.parentFile, "$name.part")
        part.writeBytes(bytes)
        if (dest.exists()) dest.delete()
        part.renameTo(dest)
        return dest
    }

    fun writeMeta(meta: Map<String, String>, files: List<String> = emptyList()) {
        val id = meta["id"] ?: return
        val dest = file(id, META) ?: return
        dest.parentFile?.mkdirs()
        val obj = JSONObject()
            .put("id", id)
            .put("title", meta["title"] ?: "")
            .put("artist", meta["artist"] ?: "")
            .put("language", meta["language"] ?: "zh")
            .put("status", meta["status"] ?: "ready")
            .put("files", JSONArray(files.ifEmpty { listFiles(id) }))
            .put("media_rev", meta["media_rev"] ?: "")
        dest.writeText(obj.toString())
    }

    fun getSong(songId: String): CachedSong? {
        if (!safeId(songId)) return null
        val dir = File(root, songId)
        if (!dir.isDirectory) return null
        val onDisk = listFiles(songId)
        val metaFile = File(dir, META)
        val meta = if (metaFile.exists()) JSONObject(metaFile.readText()) else JSONObject()
        val files = if (onDisk.isNotEmpty()) onDisk else jsonStrings(meta.optJSONArray("files"))
        return CachedSong(
            id = songId,
            title = meta.optString("title").ifBlank { songId },
            artist = meta.optString("artist"),
            language = meta.optString("language", "zh"),
            status = meta.optString("status", "ready"),
            files = files,
            singable = isSingable(files.toSet()),
            mediaRev = meta.optString("media_rev"),
        )
    }

    fun listSongs(): List<CachedSong> {
        return root.listFiles()
            ?.filter { it.isDirectory && safeId(it.name) }
            ?.mapNotNull { getSong(it.name) }
            ?.sortedBy { it.title }
            ?: emptyList()
    }

    fun listReady(): List<CachedSong> = listSongs().filter { it.singable }

    fun delete(songId: String) {
        val dir = File(root, songId)
        if (safeId(songId) && dir.exists()) dir.deleteRecursively()
    }

    fun catalogJson(): String {
        val songs = listReady()
        return JSONObject()
            .put("songs", JSONArray(songs.map { it.toJson() }))
            .put("total", songs.size)
            .put("source", "cache")
            .toString()
    }

    fun songJson(songId: String): String? = getSong(songId)?.toJson()?.toString()

    private fun listFiles(songId: String): List<String> {
        val dir = File(root, songId)
        return dir.listFiles()
            ?.filter { it.isFile && it.name != META && !it.name.endsWith(".part") }
            ?.map { it.name }
            ?.sorted()
            ?: emptyList()
    }

    companion object {
        const val META = "song.json"
        /**
         * Pull order matters: a song becomes pickable as soon as it is singable,
         * so both playback tracks must land before the multi-hundred-megabyte
         * video. Fetching mtv.mp4 first left original.mp3 missing while the song
         * was already on the remote, and the TV degraded to the backing track.
         */
        val WANTED = listOf(
            "karaoke.m4a",
            "original.mp3",
            "lyrics.json",
            "guide.m4a",
            "skeleton.json",
            "cover.jpg",
            "mtv.mp4",
        )

        fun parsePath(path: String): Pair<String, String>? {
            val clean = path.substringBefore('?')
            val match = Regex("^/media/([^/]+)/([^/]+)$").matchEntire(clean) ?: return null
            val id = match.groupValues[1]
            val name = match.groupValues[2]
            if (!safeId(id) || !safeName(name)) return null
            return id to name
        }

        fun wantedFiles(remote: List<String>): List<String> {
            val set = remote.toSet()
            return WANTED.filter { it in set }
        }

        fun isSingable(files: Set<String>): Boolean {
            return "karaoke.m4a" in files && "lyrics.json" in files
        }

        fun parseRange(header: String?, size: Long): Pair<Long, Long>? {
            if (header.isNullOrBlank() || size <= 0) return null
            val match = Regex("^bytes=(\\d+)-(\\d*)$").matchEntire(header.trim()) ?: return null
            val start = match.groupValues[1].toLong()
            val end = match.groupValues[2].toLongOrNull() ?: (size - 1)
            if (start < 0 || start >= size || end < start) return null
            return start to minOf(end, size - 1)
        }

        fun safeId(value: String): Boolean = value.matches(Regex("^[A-Za-z0-9_-]{1,32}$"))

        fun safeName(value: String): Boolean {
            return value.matches(Regex("^[A-Za-z0-9._-]+$")) && !value.contains("..")
        }

        private fun jsonStrings(array: JSONArray?): List<String> {
            if (array == null) return emptyList()
            return buildList {
                for (i in 0 until array.length()) add(array.optString(i))
            }
        }
    }
}
