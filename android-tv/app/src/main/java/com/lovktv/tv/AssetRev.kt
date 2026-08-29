package com.lovktv.tv

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
}
