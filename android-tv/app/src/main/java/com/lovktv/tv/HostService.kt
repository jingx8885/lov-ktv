package com.lovktv.tv

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean

class HostService : Service() {
    @Volatile
    private var server: HostServer? = null

    @Volatile
    private var cache: MediaCache? = null

    @Volatile
    private var mic: MicReceiver? = null

    private val launching = AtomicBoolean(false)

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        ensureChannel()
        startForeground(NOTIFICATION_ID, notification("正在开启局域网服务…"))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val process = Prefs.serverUrl(this).ifBlank { Prefs.DEFAULT_SERVER }
        val current = server
        if (current != null) {
            current.processOrigin = process
            HostRuntime.processOrigin = process
            HostRuntime.lanOrigin = LanAddress.origin(HostRuntime.port)
            updateNotification()
            return START_STICKY
        }
        if (!launching.compareAndSet(false, true)) {
            return START_STICKY
        }
        Thread({
            try {
                val media = MediaCache(File(filesDir, "media"))
                cache = media
                HostRuntime.micPort = startMic()
                HostRuntime.roomCode = Prefs.roomCode(this)
                val created = HostServer(
                    assets,
                    process,
                    media,
                    assetRev = packageRev(),
                ) { code ->
                    Prefs.saveRoom(this, code)
                }
                val port = created.start()
                server = created
                HostRuntime.port = port
                Handler(Looper.getMainLooper()).post { updateNotification() }
            } catch (exc: Exception) {
                launching.set(false)
                HostRuntime.ready = false
                val text = "局域网服务启动失败：${exc.message ?: "未知错误"}"
                Handler(Looper.getMainLooper()).post {
                    startForeground(NOTIFICATION_ID, notification(text))
                }
            }
        }, "lovktv-host").start()
        return START_STICKY
    }

    override fun onDestroy() {
        mic?.stop()
        mic = null
        HostRuntime.micPort = 0
        server?.stop()
        server = null
        launching.set(false)
        HostRuntime.ready = false
        super.onDestroy()
    }

    private fun startMic(): Int {
        return try {
            val receiver = MicReceiver(LanMic.DEFAULT_PORT)
            val bound = receiver.start()
            mic = receiver
            bound
        } catch (_: Exception) {
            0
        }
    }

    private fun updateNotification() {
        val origin = HostRuntime.lanOrigin.ifBlank { "http://127.0.0.1:${HostRuntime.port}" }
        val ready = cache?.listReady()?.size ?: 0
        val extra = buildString {
            if (ready > 0) append(" · 已缓存 ${ready} 首")
            if (HostRuntime.micPort > 0) append(" · 麦 ${HostRuntime.micPort}")
        }
        startForeground(NOTIFICATION_ID, notification("局域网已开  $origin$extra"))
    }

    private fun notification(text: String): Notification {
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }
        return builder
            .setContentTitle(getString(R.string.app_name))
            .setContentText(text)
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setOngoing(true)
            .build()
    }

    private fun packageRev(): String {
        val info = packageManager.getPackageInfo(packageName, 0)
        val code = if (Build.VERSION.SDK_INT >= 28) info.longVersionCode else @Suppress("DEPRECATION") info.versionCode.toLong()
        return "%x%x".format(code, info.lastUpdateTime).take(12)
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java) ?: return
        if (manager.getNotificationChannel(CHANNEL_ID) != null) return
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, getString(R.string.host_channel), NotificationManager.IMPORTANCE_LOW),
        )
    }

    companion object {
        private const val CHANNEL_ID = "lovktv-host"
        private const val NOTIFICATION_ID = 8787

        fun ensureStarted(context: Context) {
            val app = context.applicationContext
            val intent = Intent(app, HostService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                app.startForegroundService(intent)
            } else {
                app.startService(intent)
            }
        }
    }
}
