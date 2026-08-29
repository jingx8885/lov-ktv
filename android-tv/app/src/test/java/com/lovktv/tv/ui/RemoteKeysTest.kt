package com.lovktv.tv.ui

import com.lovktv.tv.ui.RemoteKeys
import android.view.KeyEvent
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RemoteKeysTest {
    @Test
    fun dpadMapsToPlaybackActions() {
        assertEquals(null, RemoteKeys.jsAction(KeyEvent.KEYCODE_DPAD_RIGHT))
        assertEquals("skip", RemoteKeys.jsAction(KeyEvent.KEYCODE_MEDIA_NEXT))
        assertEquals("volumeUp", RemoteKeys.jsAction(KeyEvent.KEYCODE_DPAD_UP))
        assertEquals("volumeDown", RemoteKeys.jsAction(KeyEvent.KEYCODE_DPAD_DOWN))
        assertEquals("confirm", RemoteKeys.jsAction(KeyEvent.KEYCODE_DPAD_CENTER))
        assertEquals("start", RemoteKeys.jsAction(KeyEvent.KEYCODE_MEDIA_PLAY))
        assertEquals("settings", RemoteKeys.jsAction(KeyEvent.KEYCODE_MENU))
        assertEquals("back", RemoteKeys.jsAction(KeyEvent.KEYCODE_BACK))
    }

    @Test
    fun nativeOnlyInterceptsMediaKeys() {
        assertTrue(RemoteKeys.interceptInNative(KeyEvent.KEYCODE_MEDIA_NEXT))
        assertTrue(RemoteKeys.interceptInNative(KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE))
        assertTrue(RemoteKeys.interceptInNative(KeyEvent.KEYCODE_MENU))
        assertFalse(RemoteKeys.interceptInNative(KeyEvent.KEYCODE_DPAD_RIGHT))
        assertFalse(RemoteKeys.interceptInNative(KeyEvent.KEYCODE_DPAD_CENTER))
        assertFalse(RemoteKeys.interceptInNative(KeyEvent.KEYCODE_BACK))
    }
}
