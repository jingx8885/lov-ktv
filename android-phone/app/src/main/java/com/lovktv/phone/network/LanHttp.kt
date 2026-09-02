package com.lovktv.phone.network

import com.lovktv.phone.platform.Prefs
import com.lovktv.phone.ui.DeskPage

import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.HttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

object LanHttp {
    data class Result(val ok: Boolean, val status: Int, val body: String)

    /**
     * Share the WebView's cookie jar.
     *
     * Once the desk is bound to a TV, the injected `window.fetch` sends every
     * LAN request through here instead of the WebView, so without this the
     * session cookie was neither sent nor stored and the desk looked logged
     * out on every load. CookieManager is touched lazily so JVM unit tests can
     * still exercise the pure helpers.
     */
    private val cookieJar = object : CookieJar {
        override fun loadForRequest(url: HttpUrl): List<Cookie> {
            val header = runCatching {
                android.webkit.CookieManager.getInstance().getCookie(url.toString())
            }.getOrNull().orEmpty()
            if (header.isBlank()) return emptyList()
            return header.split(';').mapNotNull { Cookie.parse(url, it.trim()) }
        }

        override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
            if (cookies.isEmpty()) return
            runCatching {
                val manager = android.webkit.CookieManager.getInstance()
                for (cookie in cookies) {
                    // Cookie.toString() intentionally emits only name=value.
                    // Preserve the server path (normally `/`) when handing it
                    // to WebView; otherwise CookieManager derives `/api/auth`
                    // from the login response URL and the session disappears
                    // on room/song requests routed through the LAN host.
                    val value = buildString {
                        append(cookie.toString())
                        append("; Path=").append(cookie.path)
                        if (cookie.secure) append("; Secure")
                        if (cookie.httpOnly) append("; HttpOnly")
                    }
                    manager.setCookie(url.toString(), value)
                }
                manager.flush()
            }
        }
    }

    private val http = OkHttpClient.Builder()
        .connectTimeout(3, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .cookieJar(cookieJar)
        .build()

    fun allowed(url: String): Boolean {
        val value = url.trim()
        if (!value.startsWith("http://")) return false
        val host = DeskPage.hostOf(value)
        return host.isNotBlank() && Prefs.looksLocal(host)
    }

    fun request(url: String, method: String, body: String = ""): Result {
        if (!allowed(url)) return Result(false, 0, """{"detail":"not-lan"}""")
        val verb = method.trim().ifBlank { "GET" }.uppercase()
        val builder = Request.Builder().url(url)
        val payload = if (verb == "GET" || verb == "HEAD") null else {
            body.toRequestBody(JSON)
        }
        builder.method(verb, payload)
        builder.header("Accept", "application/json")
        builder.header("User-Agent", "LovKtv-Phone/1.0")
        return try {
            http.newCall(builder.build()).execute().use { response ->
                Result(response.isSuccessful, response.code, response.body?.string().orEmpty())
            }
        } catch (exc: Exception) {
            Result(false, 0, JSONObject().put("detail", exc.message ?: "lan-fail").toString())
        }
    }

    private val JSON = "application/json; charset=utf-8".toMediaType()
}
