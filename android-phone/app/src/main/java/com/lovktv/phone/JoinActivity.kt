package com.lovktv.phone

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.Button
import android.widget.EditText
import android.widget.TextView

class JoinActivity : Activity() {
    private val main = Handler(Looper.getMainLooper())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_join)
        val room = findViewById<EditText>(R.id.room)
        val server = findViewById<EditText>(R.id.server)
        val error = findViewById<TextView>(R.id.error)
        val enter = findViewById<Button>(R.id.enter)
        room.setText(Prefs.roomCode(this))
        server.setText(Prefs.serverUrl(this).ifBlank { Prefs.DEFAULT_SERVER })
        enter.setOnClickListener {
            val code = room.text.toString().trim().uppercase()
            val url = Prefs.normalize(server.text.toString())
            if (code.isEmpty()) {
                error.text = "先填房间码"
                return@setOnClickListener
            }
            enter.isEnabled = false
            error.text = "连接中…"
            Thread({
                try {
                    val api = ApiClient(url)
                    val host = api.host()
                    api.room(code)
                    Prefs.save(this, url, code)
                    val micReady = HostParser.lanMicReady(host)
                    main.post {
                        startActivity(
                            Intent(this, DeskActivity::class.java)
                                .putExtra(DeskActivity.EXTRA_SERVER, url)
                                .putExtra(DeskActivity.EXTRA_ROOM, code)
                                .putExtra(DeskActivity.EXTRA_MIC_HOST, HostParser.hostFromOrigin(host.origin))
                                .putExtra(DeskActivity.EXTRA_MIC_PORT, if (micReady) host.micPort else 0)
                                .putExtra(DeskActivity.EXTRA_MIC_RATE, host.micSampleRate),
                        )
                        finish()
                    }
                } catch (exc: Exception) {
                    main.post {
                        enter.isEnabled = true
                        error.text = exc.message ?: "进房失败"
                    }
                }
            }, "lovktv-join").start()
        }
    }
}
