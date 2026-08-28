package com.lovktv.tv

import android.app.Application
import android.util.Log
import java.net.BindException

class LovKtvApp : Application() {
    override fun onCreate() {
        super.onCreate()
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, error ->
            if (isBindCrash(error)) {
                Log.e("lovktv", "ignored bind crash on ${thread.name}", error)
                return@setDefaultUncaughtExceptionHandler
            }
            previous?.uncaughtException(thread, error)
        }
        Prefs.migrate(this)
        if (Prefs.serverUrl(this).isNotBlank()) {
            HostService.ensureStarted(this)
        }
    }

    private fun isBindCrash(error: Throwable): Boolean {
        var current: Throwable? = error
        while (current != null) {
            if (current is BindException) return true
            current = current.cause
        }
        return false
    }
}
