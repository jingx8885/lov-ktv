package com.lovktv.phone.feature

import android.app.Activity
import android.content.Intent
import android.os.Bundle

class JoinActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        startActivity(Intent(this, DeskActivity::class.java))
        finish()
    }
}
