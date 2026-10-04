package com.lovktv.phone.platform

import com.lovktv.phone.R

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.widget.Toast

/**
 * PackageInstaller reports session results here. Forward its
 * STATUS_PENDING_USER_ACTION prompt so the system confirmation screen appears,
 * and toast the outcome otherwise.
 */
class UpdateInstallReceiver : BroadcastReceiver() {
    @Suppress("DEPRECATION")
    override fun onReceive(context: Context, intent: Intent) {
        when (intent.getIntExtra(PackageInstaller.EXTRA_STATUS, -1)) {
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                val confirm = intent.getParcelableExtra<Intent>(Intent.EXTRA_INTENT)
                if (confirm != null) {
                    confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    context.startActivity(confirm)
                }
            }
            PackageInstaller.STATUS_SUCCESS -> {
                Toast.makeText(context, R.string.upd_installed, Toast.LENGTH_LONG).show()
            }
            else -> {
                val detail = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE)
                    ?: intent.getIntExtra(PackageInstaller.EXTRA_STATUS, -1).toString()
                Toast.makeText(
                    context,
                    context.getString(R.string.upd_install_fail) + " " + detail,
                    Toast.LENGTH_LONG,
                ).show()
            }
        }
    }
}
