package com.lovktv.phone

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.ListView
import android.widget.TextView
import android.widget.Toast

class DeskActivity : Activity() {
    private enum class Tab { SEARCH, QUEUE, LIBRARY }

    private val main = Handler(Looper.getMainLooper())
    private lateinit var api: ApiClient
    private lateinit var adapter: RowAdapter
    private var tab = Tab.SEARCH
    private var roomCode = ""
    private var micHost = ""
    private var micPort = 0
    private var micRate = LanMic.SAMPLE_RATE
    private var lastQuery = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_desk)
        val server = intent.getStringExtra(EXTRA_SERVER).orEmpty().ifBlank { Prefs.serverUrl(this) }
        roomCode = intent.getStringExtra(EXTRA_ROOM).orEmpty().ifBlank { Prefs.roomCode(this) }
        micHost = intent.getStringExtra(EXTRA_MIC_HOST).orEmpty()
        micPort = intent.getIntExtra(EXTRA_MIC_PORT, 0)
        micRate = intent.getIntExtra(EXTRA_MIC_RATE, LanMic.SAMPLE_RATE)
        api = ApiClient(server)
        findViewById<TextView>(R.id.roomTitle).text = "房间 $roomCode"
        adapter = RowAdapter(layoutInflater) { row -> handleAction(row) }
        findViewById<ListView>(R.id.list).adapter = adapter
        findViewById<Button>(R.id.tabSearch).setOnClickListener { showTab(Tab.SEARCH) }
        findViewById<Button>(R.id.tabQueue).setOnClickListener { showTab(Tab.QUEUE) }
        findViewById<Button>(R.id.tabLibrary).setOnClickListener { showTab(Tab.LIBRARY) }
        findViewById<Button>(R.id.search).setOnClickListener { runSearch() }
        findViewById<Button>(R.id.mic).setOnClickListener { toggleMic() }
        refreshMicUi()
        showTab(Tab.SEARCH)
        pollRoom()
    }

    override fun onDestroy() {
        main.removeCallbacksAndMessages(null)
        super.onDestroy()
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        if (requestCode == REQ_MIC && grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) {
            startMic()
        } else if (requestCode == REQ_MIC) {
            toast("需要麦克风权限才能开麦")
        }
    }

    private fun showTab(next: Tab) {
        tab = next
        findViewById<View>(R.id.searchBar).visibility = if (next == Tab.SEARCH) View.VISIBLE else View.GONE
        paintTabs()
        when (next) {
            Tab.SEARCH -> if (lastQuery.isNotBlank()) runSearch() else adapter.replace(emptyList())
            Tab.QUEUE -> loadRoom()
            Tab.LIBRARY -> loadSongs()
        }
    }

    private fun paintTabs() {
        fun color(button: Button, on: Boolean) {
            button.setBackgroundColor(if (on) 0xFFFF4D8D.toInt() else 0xFF151B2E.toInt())
        }
        color(findViewById(R.id.tabSearch), tab == Tab.SEARCH)
        color(findViewById(R.id.tabQueue), tab == Tab.QUEUE)
        color(findViewById(R.id.tabLibrary), tab == Tab.LIBRARY)
    }

    private fun runSearch() {
        val query = findViewById<EditText>(R.id.query).text.toString().trim()
        if (query.isEmpty()) return
        lastQuery = query
        io {
            val hits = api.search(query)
            main.post {
                adapter.replace(
                    hits.map { hit ->
                        RowAdapter.Row(
                            key = "hit:${hit.id}",
                            title = hit.title.ifBlank { "未命名" },
                            meta = listOf(hit.artist, hit.source).filter { it.isNotBlank() }.joinToString(" · "),
                            action = "入库",
                            payload = hit,
                        )
                    },
                )
            }
        }
    }

    private fun loadSongs() {
        io {
            val songs = api.songs()
            main.post {
                adapter.replace(
                    songs.map { song ->
                        RowAdapter.Row(
                            key = "song:${song.id}",
                            title = song.title.ifBlank { "未命名" },
                            meta = listOf(song.artist, statusLabel(song.status)).filter { it.isNotBlank() }.joinToString(" · "),
                            action = if (song.ready) "点歌" else "制作中",
                            enabled = song.ready,
                            payload = song,
                        )
                    },
                )
            }
        }
    }

    private fun loadRoom() {
        io {
            val room = api.room(roomCode)
            main.post { renderRoom(room) }
        }
    }

    private fun pollRoom() {
        if (isFinishing || isDestroyed) return
        loadRoom()
        main.postDelayed({ pollRoom() }, 2500)
    }

    private fun renderRoom(room: RoomView) {
        val now = if (room.nowTitle.isBlank()) "还没开始唱" else "在唱 ${room.nowTitle}  ${room.nowArtist}"
        findViewById<TextView>(R.id.nowPlaying).text = now
        if (tab != Tab.QUEUE) return
        adapter.replace(
            room.queue.map { song ->
                RowAdapter.Row(
                    key = "queue:${song.id}",
                    title = song.title.ifBlank { "未命名" },
                    meta = listOf(song.artist, statusLabel(song.status)).filter { it.isNotBlank() }.joinToString(" · "),
                    action = "已点",
                    enabled = false,
                    payload = song,
                )
            },
        )
    }

    private fun handleAction(row: RowAdapter.Row) {
        when (val payload = row.payload) {
            is SearchHit -> importHit(payload)
            is SongRow -> queueSong(payload.id)
        }
    }

    private fun importHit(hit: SearchHit) {
        val query = lastQuery.ifBlank { hit.title }
        io {
            val created = api.importHit(query, hit)
            main.post {
                toast(if (created.isBlank()) "入库失败" else "已加入曲库，做好了再点")
                showTab(Tab.LIBRARY)
            }
        }
    }

    private fun queueSong(songId: String) {
        io {
            api.queue(roomCode, songId)
            main.post {
                toast("已点")
                showTab(Tab.QUEUE)
            }
        }
    }

    private fun toggleMic() {
        if (micPort <= 0 || micHost.isBlank()) {
            toast(getString(R.string.mic_need_tv))
            return
        }
        if (MicService.running) {
            MicService.stop(this)
            refreshMicUi()
            return
        }
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            val extra = mutableListOf(Manifest.permission.RECORD_AUDIO)
            if (Build.VERSION.SDK_INT >= 33) extra.add(Manifest.permission.POST_NOTIFICATIONS)
            requestPermissions(extra.toTypedArray(), REQ_MIC)
            return
        }
        startMic()
    }

    private fun startMic() {
        MicService.start(this, micHost, micPort, micRate)
        refreshMicUi()
    }

    private fun refreshMicUi() {
        val button = findViewById<Button>(R.id.mic)
        val hint = findViewById<TextView>(R.id.micHint)
        val ready = micPort > 0 && micHost.isNotBlank()
        button.isEnabled = ready
        button.text = if (MicService.running) getString(R.string.mic_on) else getString(R.string.mic_off)
        hint.text = when {
            MicService.running -> "麦已开 · UDP $micHost:$micPort"
            ready -> "低延时麦发到电视 $micHost:$micPort，请离音箱远一点"
            else -> getString(R.string.mic_need_tv)
        }
    }

    private fun io(block: () -> Unit) {
        Thread({
            try {
                block()
            } catch (exc: Exception) {
                main.post { toast(exc.message ?: "失败") }
            }
        }, "lovktv-desk").start()
    }

    private fun toast(text: String) {
        Toast.makeText(this, text, Toast.LENGTH_SHORT).show()
    }

    private fun statusLabel(status: String): String {
        return when (status) {
            "ready" -> "可唱"
            "separating" -> "分离中"
            "aligning" -> "对齐中"
            "failed" -> "失败"
            else -> status
        }
    }

    companion object {
        const val EXTRA_SERVER = "server"
        const val EXTRA_ROOM = "room"
        const val EXTRA_MIC_HOST = "mic_host"
        const val EXTRA_MIC_PORT = "mic_port"
        const val EXTRA_MIC_RATE = "mic_rate"
        private const val REQ_MIC = 21
    }
}
