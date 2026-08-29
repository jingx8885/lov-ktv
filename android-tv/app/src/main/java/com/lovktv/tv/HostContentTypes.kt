package com.lovktv.tv

import io.ktor.http.ContentType
import io.ktor.http.withCharset

/** Content types shared by the embedded HTTP handlers. */
object HostContentTypes {
    fun mime(name: String): ContentType {
        return when {
            name.endsWith(".html") -> ContentType.Text.Html.withCharset(Charsets.UTF_8)
            name.endsWith(".css") -> ContentType.Text.CSS.withCharset(Charsets.UTF_8)
            name.endsWith(".js") -> ContentType.Application.JavaScript.withCharset(Charsets.UTF_8)
            name.endsWith(".json") -> ContentType.Application.Json
            name.endsWith(".svg") -> ContentType.parse("image/svg+xml")
            name.endsWith(".png") -> ContentType.Image.PNG
            name.endsWith(".jpg") || name.endsWith(".jpeg") -> ContentType.Image.JPEG
            name.endsWith(".m4a") -> ContentType.parse("audio/mp4")
            name.endsWith(".mp3") -> ContentType.parse("audio/mpeg")
            name.endsWith(".mp4") -> ContentType.parse("video/mp4")
            else -> ContentType.Application.OctetStream
        }
    }
}
