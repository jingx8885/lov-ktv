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
    private lateinit var room: EditText
    private lateinit var server: EditText
    private lateinit var error: TextView
    private lateinit var enter: Button
    private lateinit var scan: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_join)
        room = findViewById(R.id.room)
        server = findViewById(R.id.server)
        error = findViewById(R.id.error)
        enter = findViewById(R.id.enter)
        scan = findViewById(R.id.scan)
        room.setText(Prefs.roomCode(this))
        server.setText(Prefs.serverUrl(this).ifBlank { Prefs.DEFAULT_SERVER })
        scan.setOnClickListener { ScanActivity.start(this) }
        enter.setOnClickListener {
            joinRoom(room.text.toString(), server.text.toString())
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != ScanActivity.REQ || resultCode != RESULT_OK) return
        val text = data?.getStringExtra(ScanActivity.EXTRA_TEXT).orEmpty()
        val target = JoinLink.parse(text, server.text.toString())
        if (target == null) {
            error.text = getString(R.string.scan_invalid)
            return
        }
        room.setText(target.room)
        server.setText(target.server)
        joinRoom(target.room, target.server, target.lan)
    }

    private fun joinRoom(codeRaw: String, serverRaw: String, lanRaw: String = "") {
        val code = codeRaw.trim().uppercase()
        val url = Prefs.normalize(serverRaw)
        val lan = lanRaw.ifBlank { Prefs.lanUrl(this) }
        if (code.isEmpty()) {
            error.text = "先填房间码"
            return
        }
        enter.isEnabled = false
        scan.isEnabled = false
        error.text = "连接中…"
        Thread({
            try {
                val session = RoomConnect.open(url, code, lan)
                Prefs.save(this, session.server, session.room, session.lanOrigin)
                main.post {
                    startActivity(
                        Intent(this, DeskActivity::class.java)
                            .putExtra(DeskActivity.EXTRA_SERVER, session.server)
                            .putExtra(DeskActivity.EXTRA_ROOM, session.room)
                            .putExtra(DeskActivity.EXTRA_LAN, session.lanOrigin)
                            .putExtra(DeskActivity.EXTRA_MIC_HOST, session.micHost)
                            .putExtra(DeskActivity.EXTRA_MIC_PORT, session.micPort)
                            .putExtra(DeskActivity.EXTRA_MIC_RATE, session.micRate),
                    )
                    finish()
                }
            } catch (exc: Exception) {
                main.post {
                    enter.isEnabled = true
                    scan.isEnabled = true
                    error.text = exc.message ?: "进房失败"
                }
            }
        }, "lovktv-join").start()
    }
}
