package com.lovktv.phone.network

import com.lovktv.phone.platform.Prefs
import com.lovktv.phone.ui.DeskPage

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

object LanHttp {
    data class Result(val ok: Boolean, val status: Int, val body: String)

    private val http = OkHttpClient.Builder()
        .connectTimeout(3, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
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
