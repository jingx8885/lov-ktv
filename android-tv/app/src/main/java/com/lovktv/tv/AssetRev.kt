package com.lovktv.tv

import android.content.res.AssetManager
import org.json.JSONObject

object AssetRev {
    private val REF = Regex(
        """(url\(|['"`])((?:\.{1,2}/|/)(?:[\w.-]+/)*[\w.-]+\.(?:js|css))(?:\?v=[^'"`?\s#&]*)?(['"`)])""",
    )

    fun rewrite(text: String, rev: String): String {
        if (rev.isBlank()) return text
        return REF.replace(text) { match ->
            "${match.groupValues[1]}${match.groupValues[2]}?v=$rev${match.groupValues[3]}"
        }
    }

    fun shouldRewrite(name: String): Boolean {
        return name.endsWith(".html") || name.endsWith(".js") || name.endsWith(".css")
    }

    fun fromManifest(assets: AssetManager): String {
        return try {
            assets.open("web/manifest.json").use { input ->
                fromManifestJson(input.bufferedReader(Charsets.UTF_8).readText())
            }
        } catch (_: Exception) {
            ""
        }
    }

    fun fromManifestJson(text: String): String {
        return runCatching { JSONObject(text).optString("revision").trim() }.getOrDefault("")
    }
}
