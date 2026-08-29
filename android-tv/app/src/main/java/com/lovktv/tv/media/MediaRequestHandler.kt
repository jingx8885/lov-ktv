package com.lovktv.tv.media


import com.lovktv.tv.feature.host.HostContentTypes
import com.lovktv.tv.feature.host.HostGateway
import io.ktor.http.HttpHeaders
import io.ktor.server.application.ApplicationCall
import io.ktor.server.response.respond
import io.ktor.server.response.respondBytes
import io.ktor.utils.io.ByteWriteChannel
import io.ktor.utils.io.writeFully
import io.ktor.http.content.OutgoingContent
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File

/** Reads media from the local cache and fills cache misses from the process API. */
class MediaRequestHandler(
    private val cache: MediaCache,
    private val apiHttp: OkHttpClient,
    private val processOrigin: () -> String,
    private val hintPuller: () -> Unit,
    private val proxy: suspend (ApplicationCall) -> Unit,
) {
    companion object {
        fun shouldCacheName(name: String): Boolean = name.endsWith(".json") || name == "cover.jpg"
    }

    suspend fun serve(call: ApplicationCall, songId: String, name: String) {
        val rev = call.request.queryParameters["v"].orEmpty()
        val local = cache.file(songId, name)
        val cachedRev = cache.getSong(songId)?.mediaRev.orEmpty()
        val fresh = local != null && local.exists() && local.length() > 0 &&
            (rev.isBlank() || cachedRev.isBlank() || cachedRev == rev)
        if (fresh) {
            serveFile(call, local!!)
            return
        }
        hintPuller()
        if (shouldCacheName(name)) {
            val bytes = withContext(Dispatchers.IO) { fetch(songId, name, rev) }
            if (bytes != null && bytes.isNotEmpty()) {
                cache.putFile(songId, name, bytes)
                call.response.headers.append(HttpHeaders.CacheControl, cacheControl(call))
                call.response.headers.append("Access-Control-Allow-Origin", "*")
                call.respondBytes(bytes, HostContentTypes.mime(name))
                return
            }
        }
        proxy(call)
    }

    fun cacheControl(call: ApplicationCall): String {
        return if (call.request.queryParameters["v"].orEmpty().isNotBlank()) {
            "public, max-age=31536000, immutable"
        } else {
            "no-cache, must-revalidate"
        }
    }

    private fun fetch(songId: String, name: String, rev: String): ByteArray? {
        return try {
            val query = if (rev.isNotBlank()) "v=$rev" else null
            val remote = HostGateway.remoteUrl(processOrigin(), "/media/$songId/$name", query)
            val request = Request.Builder().url(remote).header("Accept", "*/*")
                .header("User-Agent", "LovKtv-TV/1.0").build()
            apiHttp.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    android.util.Log.w("MediaRequestHandler", "fetchMedia $songId/$name -> ${response.code}")
                    return null
                }
                val bytes = response.body?.bytes() ?: return null
                if (bytes.size > 2_000_000) return null
                bytes
            }
        } catch (exc: Exception) {
            android.util.Log.w("MediaRequestHandler", "fetchMedia $songId/$name failed: ${exc.message}")
            null
        }
    }

    private suspend fun serveFile(call: ApplicationCall, file: File) {
        val size = file.length()
        val range = MediaCache.parseRange(call.request.headers[HttpHeaders.Range], size)
        val type = HostContentTypes.mime(file.name)
        call.response.headers.append(HttpHeaders.AcceptRanges, "bytes")
        call.response.headers.append(HttpHeaders.CacheControl, cacheControl(call))
        call.response.headers.append("Access-Control-Allow-Origin", "*")
        if (range == null) {
            call.respond(fileContent(file, type, HttpStatus.OK, size))
            return
        }
        val (start, end) = range
        val length = end - start + 1
        call.respond(fileContent(file, type, HttpStatus.Partial, length, start, end, size))
    }

    private fun fileContent(
        file: File,
        type: io.ktor.http.ContentType,
        status: HttpStatus,
        length: Long,
        start: Long = 0,
        end: Long = file.length() - 1,
        total: Long = file.length(),
    ): OutgoingContent.WriteChannelContent {
        return object : OutgoingContent.WriteChannelContent() {
            override val status = if (status == HttpStatus.OK) io.ktor.http.HttpStatusCode.OK else io.ktor.http.HttpStatusCode.PartialContent
            override val contentType = type
            override val contentLength = length
            override val headers = if (status == HttpStatus.Partial) io.ktor.http.Headers.build {
                append(HttpHeaders.ContentRange, "bytes $start-$end/$total")
                append(HttpHeaders.AcceptRanges, "bytes")
            } else io.ktor.http.Headers.build { }
            override suspend fun writeTo(channel: ByteWriteChannel) {
                file.inputStream().use { input ->
                    if (start > 0) withContext(Dispatchers.IO) { input.skip(start) }
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
        }
    }

    private enum class HttpStatus { OK, Partial }
}
