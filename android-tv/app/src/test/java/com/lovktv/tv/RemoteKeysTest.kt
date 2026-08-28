package com.lovktv.tv

import android.view.KeyEvent
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RemoteKeysTest {
    @Test
    fun dpadMapsToPlaybackActions() {
        assertEquals("skip", RemoteKeys.jsAction(KeyEvent.KEYCODE_DPAD_RIGHT))
        assertEquals("volumeUp", RemoteKeys.jsAction(KeyEvent.KEYCODE_DPAD_UP))
        assertEquals("volumeDown", RemoteKeys.jsAction(KeyEvent.KEYCODE_DPAD_DOWN))
        assertEquals("confirm", RemoteKeys.jsAction(KeyEvent.KEYCODE_DPAD_CENTER))
        assertEquals("start", RemoteKeys.jsAction(KeyEvent.KEYCODE_MEDIA_PLAY))
    }

    @Test
    fun nativeOnlyInterceptsMediaKeys() {
        assertTrue(RemoteKeys.interceptInNative(KeyEvent.KEYCODE_MEDIA_NEXT))
        assertTrue(RemoteKeys.interceptInNative(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE))
        assertFalse(RemoteKeys.interceptInNative(KeyEvent.KEYCODE_DPAD_RIGHT))
        assertFalse(RemoteKeys.interceptInNative(KeyEvent.KEYCODE_DPAD_CENTER))
        assertFalse(RemoteKeys.interceptInNative(KeyEvent.KEYCODE_BACK))
    }
}
