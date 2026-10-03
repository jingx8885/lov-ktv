package com.lovktv.phone.media

import android.app.Notification
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager

/**
 * Foreground companion for WebView listening.
 *
 * The phone player renders inside a WebView, so there is no native audio
 * pipeline Android can attribute playback to.  Without a mediaPlayback
 * foreground service the OS is free to suspend the WebView's timers and
 * eventually the process once the screen goes off, which stops audio between
 * tracks and hides the notification shade controls.
 */
class PlaybackService : Service() {
    private var wakeLock: PowerManager.WakeLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val notif = latest
        if (!playing || notif == null) {
            shutdown()
            return START_NOT_STICKY
        }
        acquireWakeLock()
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(NOTIFICATION_ID, notif, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK)
            } else {
                startForeground(NOTIFICATION_ID, notif)
            }
        } catch (_: Exception) {
            // Android 14+ can refuse the start if the mediaPlayback type is not
            // permitted; the notification still exists via the controller.
        }
        return START_STICKY
    }

    override fun onDestroy() {
        running = false
        releaseWakeLock()
        super.onDestroy()
    }

    private fun acquireWakeLock() {
        if (wakeLock?.isHeld == true) return
        val pm = getSystemService(PowerManager::class.java) ?: return
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, WAKE_TAG).apply {
            setReferenceCounted(false)
            acquire()
        }
    }

    private fun releaseWakeLock() {
        try {
            wakeLock?.let { if (it.isHeld) it.release() }
        } catch (_: Exception) {
        }
        wakeLock = null
    }

    private fun shutdown() {
        playing = false
        latest = null
        releaseWakeLock()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_DETACH)
        } else {
            @Suppress("DEPRECATION")
            stopForeground(false)
        }
        stopSelf()
        running = false
    }


    companion object {
        /** Same id as PhoneNotificationController so the foreground post
         * replaces the shade notification instead of duplicating it. */
        private const val NOTIFICATION_ID = 4101
        private const val WAKE_TAG = "lovktv:phone-playback"

        @Volatile
        var running = false
            private set

        @Volatile
        private var playing = false

        @Volatile
        private var latest: Notification? = null

        /** Keep the shade controls alive while audio is playing. */
        fun sync(context: Context, isPlaying: Boolean, notification: Notification?) {
            playing = isPlaying
            latest = notification
            if (!isPlaying || notification == null) {
                stop(context)
                return
            }
            val app = context.applicationContext
            val intent = Intent(app, PlaybackService::class.java)
            running = true
            try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    app.startForegroundService(intent)
                } else {
                    app.startService(intent)
                }
            } catch (_: Exception) {
                running = false
            }
        }

        fun stop(context: Context) {
            playing = false
            latest = null
            if (!running) return
            try {
                context.applicationContext.stopService(Intent(context.applicationContext, PlaybackService::class.java))
            } catch (_: Exception) {
            }
        }
    }
}
