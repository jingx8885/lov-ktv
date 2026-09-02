package com.lovktv.phone.platform

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.media.session.MediaSession
import android.media.MediaMetadata
import android.media.session.PlaybackState
import android.os.Build
import com.lovktv.phone.R
import com.lovktv.phone.feature.DeskActivity
import org.json.JSONObject

/**
 * The notification shade companion for the phone WebView.
 *
 * The web shell tells us which page is visible and which song is current.  We
 * deliberately keep the action ids semantic (rather than depending on DOM
 * labels) so translations and styling changes do not break the shade controls.
 */
class PhoneNotificationController(private val context: Context) {
    private val manager = context.getSystemService(NotificationManager::class.java)
    private val mediaSession = MediaSession(context, "lov-ktv-phone")
    private var lastPayload = ""
    private var lastPage = "desk"

    init {
        if (Build.VERSION.SDK_INT >= 26) {
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, context.getString(R.string.notification_channel), NotificationManager.IMPORTANCE_LOW).apply {
                    description = context.getString(R.string.notification_channel_desc)
                    setShowBadge(false)
                },
            )
        }
        mediaSession.setCallback(object : MediaSession.Callback() {
            override fun onPlay() = DeskActivity.dispatchNotificationAction(context, if (lastPage == "player") ACTION_PLAYER_PLAY else ACTION_DESK_PAUSE)
            override fun onPause() = DeskActivity.dispatchNotificationAction(context, if (lastPage == "player") ACTION_PLAYER_PLAY else ACTION_DESK_PAUSE)
            override fun onSkipToNext() = DeskActivity.dispatchNotificationAction(context, if (lastPage == "player") ACTION_PLAYER_NEXT else ACTION_DESK_SKIP)
        })
        mediaSession.isActive = true
    }

    fun update(payloadJson: String) {
        val payload = runCatching { JSONObject(payloadJson) }.getOrNull() ?: return
        val page = payload.optString("page").ifBlank { "desk" }
        val title = payload.optString("title").trim()
        val artist = payload.optString("artist").trim()
        val playing = payload.optBoolean("playing", false)
        val key = listOf(page, title, artist, playing).joinToString("\u0000")
        if (key == lastPayload) return
        lastPayload = key
        lastPage = page

        val listening = page == "player"
        val label = if (listening) context.getString(R.string.notification_listening) else context.getString(R.string.notification_karaoke)
        val songTitle = title.ifBlank { context.getString(if (listening) R.string.notification_idle_listen else R.string.notification_idle_karaoke) }
        val songLine = if (artist.isBlank()) songTitle else "$songTitle · $artist"
        mediaSession.setMetadata(
            MediaMetadata.Builder()
                .putString(MediaMetadata.METADATA_KEY_TITLE, songTitle)
                .putString(MediaMetadata.METADATA_KEY_ARTIST, artist)
                .putString(MediaMetadata.METADATA_KEY_ALBUM, label)
                .build(),
        )
        mediaSession.setPlaybackState(
            PlaybackState.Builder()
                .setState(if (playing) PlaybackState.STATE_PLAYING else PlaybackState.STATE_PAUSED, 0L, 1f)
                .setActions(PlaybackState.ACTION_PLAY or PlaybackState.ACTION_PAUSE or PlaybackState.ACTION_SKIP_TO_NEXT)
                .build(),
        )
        val openIntent = Intent(context, DeskActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra(DeskActivity.EXTRA_NOTIFICATION_PAGE, page)
        }
        val content = PendingIntent.getActivity(context, REQUEST_OPEN, openIntent, pendingFlags())

        val builder = Notification.Builder(context)
            .setSmallIcon(R.drawable.ic_app)
            .setContentTitle(songLine)
            .setContentText(label)
            .setSubText(context.getString(R.string.app_name))
            .setContentIntent(content)
            .setCategory(Notification.CATEGORY_TRANSPORT)
            .setVisibility(Notification.VISIBILITY_PUBLIC)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setShowWhen(false)

        val actions = if (listening) {
            listOf(
                action(android.R.drawable.ic_menu_revert, context.getString(R.string.notification_to_karaoke), ACTION_TO_DESK),
                action(if (playing) android.R.drawable.ic_media_pause else android.R.drawable.ic_media_play, if (playing) context.getString(R.string.notification_pause) else context.getString(R.string.notification_play), ACTION_PLAYER_PLAY),
                action(android.R.drawable.ic_media_next, context.getString(R.string.notification_next), ACTION_PLAYER_NEXT),
                action(android.R.drawable.ic_btn_speak_now, context.getString(R.string.notification_vocal), ACTION_PLAYER_VOCAL),
            )
        } else {
            listOf(
                action(android.R.drawable.ic_menu_search, context.getString(R.string.notification_search), ACTION_SEARCH),
                action(if (playing) android.R.drawable.ic_media_pause else android.R.drawable.ic_media_play, if (playing) context.getString(R.string.notification_pause) else context.getString(R.string.notification_play), ACTION_DESK_PAUSE),
                action(android.R.drawable.ic_media_next, context.getString(R.string.notification_skip), ACTION_DESK_SKIP),
                action(android.R.drawable.ic_btn_speak_now, context.getString(R.string.notification_mic), ACTION_DESK_MIC),
            )
        }
        actions.forEach(builder::addAction)
        if (Build.VERSION.SDK_INT >= 21) {
            builder.setStyle(
                Notification.MediaStyle()
                    .setMediaSession(mediaSession.sessionToken)
                    .setShowActionsInCompactView(0, 1, 2),
            )
        }
        manager.notify(NOTIFICATION_ID, builder.build())
    }

    fun close() {
        manager.cancel(NOTIFICATION_ID)
        mediaSession.isActive = false
        mediaSession.release()
    }

    private fun action(icon: Int, title: String, action: String): Notification.Action {
        val intent = Intent(context, NotificationActionReceiver::class.java)
            .putExtra(EXTRA_ACTION, action)
            .putExtra(EXTRA_PAGE, lastPage)
        val pending = PendingIntent.getBroadcast(context, action.hashCode(), intent, pendingFlags())
        return Notification.Action.Builder(icon, title, pending).build()
    }

    private fun pendingFlags(): Int {
        var flags = PendingIntent.FLAG_UPDATE_CURRENT
        if (Build.VERSION.SDK_INT >= 23) flags = flags or PendingIntent.FLAG_IMMUTABLE
        return flags
    }

    companion object {
        const val EXTRA_ACTION = "lovktv.notification.action"
        const val EXTRA_PAGE = "lovktv.notification.page"
        const val ACTION_SEARCH = "search"
        const val ACTION_TO_DESK = "desk"
        const val ACTION_DESK_PAUSE = "desk_pause"
        const val ACTION_DESK_SKIP = "desk_skip"
        const val ACTION_DESK_MIC = "desk_mic"
        const val ACTION_PLAYER_PLAY = "player_play"
        const val ACTION_PLAYER_NEXT = "player_next"
        const val ACTION_PLAYER_VOCAL = "player_vocal"
        private const val CHANNEL_ID = "lovktv_playback"
        private const val NOTIFICATION_ID = 4101
        private const val REQUEST_OPEN = 4102
    }
}

class NotificationActionReceiver : android.content.BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.getStringExtra(PhoneNotificationController.EXTRA_ACTION).orEmpty()
        val page = intent.getStringExtra(PhoneNotificationController.EXTRA_PAGE).orEmpty()
        if (action.isNotBlank()) DeskActivity.dispatchNotificationAction(context, action, page)
    }
}
