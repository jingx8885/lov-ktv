package com.lovktv.phone.feature

import com.lovktv.phone.R
import com.lovktv.phone.platform.Prefs

import android.app.Activity
import android.content.Intent
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.widget.Button
import android.widget.ImageView
import android.widget.TextView
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class SplashActivity : Activity() {
    private val main = Handler(Looper.getMainLooper())
    private val http = OkHttpClient.Builder()
        .connectTimeout(4, TimeUnit.SECONDS)
        .readTimeout(8, TimeUnit.SECONDS)
        .build()
    private var token = ""
    private var remain = 30
    private var jumpUrl = ""
    private var finished = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_splash)
        findViewById<TextView>(R.id.adSkip).setOnClickListener { goDesk() }
        findViewById<Button>(R.id.adJump).setOnClickListener { jump() }
        Thread { loadAd() }.start()
        main.postDelayed({
            findViewById<TextView>(R.id.adSkip).visibility = View.VISIBLE
        }, 5000)
    }

    private fun loadAd() {
        try {
            val server = Prefs.normalize(Prefs.serverUrl(this).ifBlank { Prefs.DEFAULT_SERVER })
            val start = post(
                "$server/api/ads/start",
                JSONObject().put("placement", "splash").toString(),
            )
            val ad = start.optJSONObject("ad")
            val nextToken = start.optString("token")
            // No upstream ad is a normal no-op. Leave the splash immediately
            // instead of rendering an empty card or starting a fake timer.
            if (ad == null || ad.optString("id").isBlank() || nextToken.isBlank()) {
                main.post { goDesk() }
                return
            }
            token = nextToken
            remain = ad.optInt("seconds", 30).coerceAtLeast(5)
            jumpUrl = ad.optString("url")
            val imageUrl = ad.optString("image")
            val bmp = if (imageUrl.isNotBlank()) {
                runCatching {
                    val bytes = getBytes(absUrl(server, imageUrl))
                    BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                }.getOrNull()
            } else {
                null
            }
            main.post {
                findViewById<TextView>(R.id.adTitle).text = ad.optString("title")
                findViewById<TextView>(R.id.adBody).text = ad.optString("body")
                findViewById<Button>(R.id.adJump).text = ad.optString("cta").ifBlank {
                    getString(R.string.ad_jump)
                }
                if (bmp != null) findViewById<ImageView>(R.id.adImage).setImageBitmap(bmp)
                tick()
            }
        } catch (_: Exception) {
            main.post { goDesk() }
        }
    }

    private fun tick() {
        if (finished) return
        findViewById<TextView>(R.id.adTimer).text = getString(R.string.ad_remain, remain)
        if (remain <= 0) {
            Thread { complete() }.start()
            return
        }
        remain -= 1
        main.postDelayed({ tick() }, 1000)
    }

    private fun complete() {
        try {
            val server = Prefs.normalize(Prefs.serverUrl(this).ifBlank { Prefs.DEFAULT_SERVER })
            post("$server/api/ads/complete", JSONObject().put("token", token).toString())
        } catch (_: Exception) {
        }
        main.post { goDesk() }
    }

    private fun jump() {
        val server = Prefs.normalize(Prefs.serverUrl(this).ifBlank { Prefs.DEFAULT_SERVER })
        Thread {
            runCatching {
                val body = post(
                    "$server/api/ads/click",
                    JSONObject().put("token", token).toString(),
                )
                jumpUrl = body.optString("url", jumpUrl)
            }
            main.post {
                if (jumpUrl.isNotBlank()) {
                    runCatching {
                        startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(jumpUrl)))
                    }
                }
            }
        }.start()
    }

    private fun goDesk() {
        if (finished) return
        finished = true
        main.removeCallbacksAndMessages(null)
        startActivity(Intent(this, DeskActivity::class.java))
        finish()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            overrideActivityTransition(
                Activity.OVERRIDE_TRANSITION_OPEN,
                android.R.anim.fade_in,
                android.R.anim.fade_out,
            )
        } else {
            @Suppress("DEPRECATION")
            overridePendingTransition(android.R.anim.fade_in, android.R.anim.fade_out)
        }
    }

    private fun machine() = Prefs.machineId(this)

    private fun absUrl(server: String, raw: String): String {
        if (raw.startsWith("http://") || raw.startsWith("https://")) return raw
        return server.trimEnd('/') + if (raw.startsWith("/")) raw else "/$raw"
    }

    private fun getBytes(url: String): ByteArray {
        val req = Request.Builder()
            .url(url)
            .header("X-LovKtv-Machine", machine())
            .build()
        http.newCall(req).execute().use { resp ->
            return resp.body?.bytes() ?: ByteArray(0)
        }
    }

    private fun post(url: String, json: String): JSONObject {
        val req = Request.Builder()
            .url(url)
            .header("X-LovKtv-Machine", machine())
            .post(json.toRequestBody(JSON))
            .build()
        http.newCall(req).execute().use { resp ->
            val text = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) throw IllegalStateException(text)
            return JSONObject(text.ifBlank { "{}" })
        }
    }

    override fun onDestroy() {
        finished = true
        main.removeCallbacksAndMessages(null)
        super.onDestroy()
    }

    companion object {
        private val JSON = "application/json; charset=utf-8".toMediaType()
    }
}
