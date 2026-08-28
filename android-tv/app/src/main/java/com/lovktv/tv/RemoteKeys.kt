package com.lovktv.tv

import android.view.KeyEvent

object RemoteKeys {
    fun jsAction(keyCode: Int): String? {
        return when (keyCode) {
            KeyEvent.KEYCODE_DPAD_RIGHT,
            KeyEvent.KEYCODE_MEDIA_NEXT,
            KeyEvent.KEYCODE_MEDIA_SKIP_FORWARD,
            KeyEvent.KEYCODE_CHANNEL_UP,
            -> "skip"
            KeyEvent.KEYCODE_DPAD_UP -> "volumeUp"
            KeyEvent.KEYCODE_DPAD_DOWN -> "volumeDown"
            KeyEvent.KEYCODE_DPAD_CENTER,
            KeyEvent.KEYCODE_ENTER,
            KeyEvent.KEYCODE_NUMPAD_ENTER,
            KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE,
            -> "confirm"
            KeyEvent.KEYCODE_MEDIA_PLAY -> "start"
            else -> null
        }
    }

    fun interceptInNative(keyCode: Int): Boolean {
        return when (keyCode) {
            KeyEvent.KEYCODE_MEDIA_NEXT,
            KeyEvent.KEYCODE_MEDIA_SKIP_FORWARD,
            KeyEvent.KEYCODE_CHANNEL_UP,
            KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE,
            KeyEvent.KEYCODE_MEDIA_PLAY,
            -> true
            else -> false
        }
    }
}
