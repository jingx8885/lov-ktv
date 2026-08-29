package com.lovktv.tv.feature.host


import com.lovktv.tv.platform.AssetRev
import android.content.res.AssetManager
import io.ktor.http.HttpHeaders
import io.ktor.server.application.ApplicationCall
import io.ktor.server.response.respond
import io.ktor.server.response.respondBytes
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.IOException

/** Serves the versioned web bundle from Android assets. */
class StaticAssetHandler(
    private val assets: AssetManager,
    private val assetRev: String,
) {
    companion object {
        fun assetNameFor(path: String): String {
            val clean = path.substringBefore('?').trimStart('/')
            val relative = if (clean.isEmpty() || clean.endsWith('/')) clean + "index.html" else clean
            return "web/$relative"
        }
    }

    suspend fun serve(call: ApplicationCall, path: String) {
        val name = assetName(path)
        val bytes = withContext(Dispatchers.IO) { readAsset(name) }
        if (bytes == null) {
            call.respond(io.ktor.http.HttpStatusCode.NotFound, "not found")
            return
        }
        val body = if (AssetRev.shouldRewrite(name) && assetRev.isNotBlank()) {
            AssetRev.rewrite(String(bytes, Charsets.UTF_8), assetRev).toByteArray(Charsets.UTF_8)
        } else {
            bytes
        }
        if (name.endsWith(".html") || name.endsWith("manifest.json")) {
            call.response.headers.append(HttpHeaders.CacheControl, "no-store, max-age=0")
            call.response.headers.append("Pragma", "no-cache")
        } else if (AssetRev.shouldRewrite(name) && assetRev.isNotBlank()) {
            call.response.headers.append(HttpHeaders.CacheControl, "public, max-age=31536000, immutable")
        }
        call.respondBytes(body, contentType = HostContentTypes.mime(name))
    }

    fun assetName(path: String): String {
        return assetNameFor(path)
    }

    private fun readAsset(name: String): ByteArray? {
        return try {
            assets.open(name).use { it.readBytes() }
        } catch (_: IOException) {
            null
        }
    }
}
