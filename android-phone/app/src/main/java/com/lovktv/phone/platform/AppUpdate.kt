package com.lovktv.phone.platform

import com.lovktv.phone.R

import android.app.Activity
import android.app.AlertDialog
import android.app.PendingIntent
import android.content.Intent
import android.content.pm.PackageInstaller
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.security.MessageDigest
import java.util.concurrent.TimeUnit

/**
 * In-app update. Each time the app comes to the foreground, read /api/apps.
 * A newer APK prompts, then downloads and hands the file to PackageInstaller
 * so the system shows its own confirmation screen.
 */
class AppUpdate(
    private val activity: Activity,
    private val channel: String,
    private val serverBase: () -> String,
) {
    private val main = Handler(Looper.getMainLooper())
    private val http = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .build()

    @Volatile private var checking = false
    @Volatile private var downloading = false
    @Volatile private var cancelDownload = false
    private var progressDialog: AlertDialog? = null
    private var progressBar: ProgressBar? = null
    private var progressText: TextView? = null
    private var pendingInstall: File? = null
    private var promptDialog: AlertDialog? = null
    private var permissionDialog: AlertDialog? = null
    private var deferred: Latest? = null
    private var deferredName = ""
    private var silentTries = 0
    private var openedCheckDone = false
    @Volatile private var foreground = false

    private val openCheck = Runnable { check(manual = false) }

    /** User opened the app. Check for a newer APK, or show one found while backgrounded. */
    fun onAppOpened() {
        foreground = true
        openedCheckDone = false
        if (downloading || pendingInstall != null) return
        if (showDeferred()) return
        if (promptShowing()) {
            openedCheckDone = true
            return
        }
        silentTries = 0
        scheduleOpenCheck()
    }

    /** Returned from another screen in this app. Show a waiting prompt, without checking again. */
    fun onAppResumed() {
        foreground = true
        if (downloading || pendingInstall != null || promptShowing()) return
        if (showDeferred()) return
        if (!openedCheckDone) scheduleOpenCheck()
    }

    private fun scheduleOpenCheck() {
        main.removeCallbacks(openCheck)
        main.postDelayed(openCheck, OPEN_DELAY_MS)
    }

    private fun showDeferred(): Boolean {
        val waiting = deferred ?: return false
        deferred = null
        val name = deferredName
        openedCheckDone = true
        main.post {
            if (!activity.isFinishing && !activity.isDestroyed) promptUpdate(waiting, name)
        }
        return true
    }

    fun onHostBackground() {
        foreground = false
        main.removeCallbacks(openCheck)
    }

    fun check(manual: Boolean) {
        if (checking || downloading || promptShowing()) return
        if (!manual && (!foreground || pendingInstall != null)) return
        checking = true
        Thread {
            val latest = runCatching { loadLatest() }.getOrNull()
            checking = false
            main.post { deliver(manual, latest) }
        }.start()
    }

    private fun deliver(manual: Boolean, latest: Latest?) {
        if (activity.isFinishing || activity.isDestroyed) return
        if (latest == null) {
            if (manual) {
                openedCheckDone = true
                toast(R.string.upd_check_fail)
            } else if (foreground && silentTries < SILENT_RETRIES) {
                silentTries += 1
                main.postDelayed(openCheck, RETRY_DELAY_MS)
            } else {
                openedCheckDone = true
            }
            return
        }
        silentTries = 0
        openedCheckDone = true
        val local = localVersion()
        if (!isNewer(latest, local.first, local.second)) {
            if (manual) toast(R.string.upd_latest)
            return
        }
        if (!manual && !foreground) {
            deferred = latest
            deferredName = local.first
            return
        }
        promptUpdate(latest, local.first)
    }

    /** Settings for "install unknown apps" returns here; resume a queued install. */
    fun onHostResume() {
        val apk = pendingInstall ?: return
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O ||
            activity.packageManager.canRequestPackageInstalls()
        ) {
            pendingInstall = null
            permissionDialog?.dismiss()
            permissionDialog = null
            install(apk)
            return
        }
        if (permissionDialog?.isShowing != true) showPermissionDialog(apk)
    }

    fun close() {
        foreground = false
        deferred = null
        main.removeCallbacksAndMessages(null)
        promptDialog?.dismiss()
        promptDialog = null
        permissionDialog?.dismiss()
        permissionDialog = null
        progressDialog?.dismiss()
        progressDialog = null
    }

    private data class Latest(
        val name: String,
        val code: Int,
        val url: String,
        val sha256: String,
        val size: Long,
    )

    /** Public catalog first. A LAN address is only a fallback when the public host is down. */
    private fun loadLatest(): Latest? {
        val primary = runCatching { serverBase().trim().trimEnd('/') }.getOrDefault("")
        val fallback = Prefs.DEFAULT_SERVER.trim().trimEnd('/')
        val preferPublic = primary.isBlank() || isPrivateBase(primary)
        val first = if (preferPublic) fallback else primary
        val second = when {
            first.equals(fallback, ignoreCase = true) && !primary.equals(first, ignoreCase = true) -> primary
            !first.equals(fallback, ignoreCase = true) -> fallback
            else -> ""
        }
        val latest = fetchOrNull(first)
        if (latest != null) return latest
        if (second.isBlank() || second.equals(first, ignoreCase = true)) return null
        return fetchOrNull(second)
    }

    private fun fetchOrNull(base: String): Latest? {
        if (base.isBlank()) return null
        return runCatching { fetchLatest(base) }.getOrNull()
    }

    private fun isPrivateBase(base: String): Boolean {
        val host = base.substringAfter("://").substringBefore('/').substringBefore(':')
        return Prefs.looksLocal(host)
    }

    private fun fetchLatest(base: String): Latest? {
        val body = http.newCall(
            Request.Builder()
                .url(base + "/api/apps")
                .header("Accept", "application/json")
                .build(),
        ).execute().use { resp ->
            if (!resp.isSuccessful) return null
            resp.body?.string().orEmpty()
        }
        val item = JSONObject(body).optJSONObject(channel) ?: return null
        val name = item.optString("version").trim()
        if (name.isBlank()) return null
        return Latest(
            name = name,
            code = remoteCode(item, name),
            url = resolveUrl(base, item.optString("url")),
            sha256 = item.optString("sha256").trim().lowercase(),
            size = item.optLong("size", 0),
        )
    }

    private fun resolveUrl(base: String, raw: String): String {
        val url = raw.trim()
        if (url.startsWith("http://") || url.startsWith("https://")) return url
        if (url.startsWith("/")) return base + url
        if (url.isNotBlank()) return base + "/" + url
        return base + "/apps/" + channel + ".apk"
    }

    /** Server versions are YYYY.M.D.N names; the APK code is YYYYMMDDNN. */
    private fun remoteCode(item: JSONObject, name: String): Int {
        val direct = item.optInt("version_code", item.optInt("code", 0))
        if (direct > 0) return direct
        val parts = name.split('.')
        if (parts.size == 4) {
            val y = parts[0].toIntOrNull() ?: return 0
            val m = parts[1].toIntOrNull() ?: return 0
            val d = parts[2].toIntOrNull() ?: return 0
            val n = parts[3].toIntOrNull() ?: return 0
            if (y in 2000..2100 && m in 1..12 && d in 1..31 && n in 0..99) {
                return y * 1_000_000 + m * 10_000 + d * 100 + n
            }
        }
        return 0
    }

    private fun localVersion(): Pair<String, Int> {
        return try {
            @Suppress("DEPRECATION")
            val info = activity.packageManager.getPackageInfo(activity.packageName, 0)
            val code = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                info.longVersionCode.toInt()
            } else {
                @Suppress("DEPRECATION") info.versionCode
            }
            info.versionName.orEmpty() to code
        } catch (_: Exception) {
            "" to 0
        }
    }

    private fun isNewer(latest: Latest, localName: String, localCode: Int): Boolean {
        if (latest.code > 0 && localCode > 0) return latest.code > localCode
        return latest.name != localName
    }

    private fun promptShowing(): Boolean = promptDialog?.isShowing == true

    private fun promptUpdate(latest: Latest, localName: String) {
        if (activity.isFinishing || activity.isDestroyed || promptShowing()) return
        deferred = null
        val dialog = dialog()
            .setTitle(R.string.upd_found)
            .setMessage(
                activity.getString(
                    R.string.upd_message,
                    latest.name,
                    localName.ifBlank { "?" },
                ),
            )
            .setPositiveButton(R.string.upd_now) { _, _ -> download(latest) }
            .setNegativeButton(R.string.upd_later, null)
            .create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE)?.requestFocus()
        }
        promptDialog = dialog
        dialog.show()
    }

    private fun dialog(): AlertDialog.Builder {
        return AlertDialog.Builder(activity, android.R.style.Theme_DeviceDefault_Dialog_Alert)
    }

    private fun download(latest: Latest) {
        if (downloading) return
        downloading = true
        cancelDownload = false
        showProgress()
        Thread {
            val apk = runCatching { downloadApk(latest) }.getOrNull()
            downloading = false
            main.post {
                progressDialog?.dismiss()
                progressDialog = null
                progressBar = null
                progressText = null
                if (apk == null) {
                    if (!cancelDownload) toast(R.string.upd_download_fail)
                } else if (!activity.isFinishing && !activity.isDestroyed) {
                    ensureCanInstall(apk)
                }
            }
        }.start()
    }

    private fun showProgress() {
        val pad = (activity.resources.displayMetrics.density * 20).toInt()
        val box = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad / 2)
        }
        progressText = TextView(activity)
        progressBar = ProgressBar(
            activity,
            null,
            android.R.attr.progressBarStyleHorizontal,
        ).apply {
            max = 100
            isIndeterminate = true
        }
        box.addView(progressText)
        box.addView(
            progressBar,
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT,
            ),
        )
        progressDialog = dialog()
            .setTitle(R.string.upd_downloading)
            .setView(box)
            .setCancelable(true)
            .setOnCancelListener { cancelDownload = true }
            .show()
    }

    private fun reportProgress(received: Long, total: Long) {
        main.post {
            val bar = progressBar ?: return@post
            if (total <= 0) {
                bar.isIndeterminate = true
                progressText?.text = (received / 1048576L).toString() + " MB"
            } else {
                bar.isIndeterminate = false
                val pct = ((received * 100L) / total).toInt().coerceIn(0, 100)
                bar.progress = pct
                progressText?.text = pct.toString() + "%"
            }
        }
    }

    private fun downloadApk(latest: Latest): File {
        val dir = File(activity.cacheDir, "updates").apply { mkdirs() }
        val apk = File(dir, "lovktv-" + channel + ".apk")
        val part = File(dir, "lovktv-" + channel + ".part")
        val digest = MessageDigest.getInstance("SHA-256")
        var received = 0L
        try {
        http.newCall(Request.Builder().url(latest.url).build()).execute().use { resp ->
            if (!resp.isSuccessful) throw IOException("http " + resp.code)
            val total = resp.body?.contentLength()?.takeIf { it > 0 } ?: latest.size
            val input = resp.body?.byteStream() ?: throw IOException("empty body")
            input.use { stream ->
                FileOutputStream(part).use { out ->
                    val buf = ByteArray(64 * 1024)
                    while (true) {
                        if (cancelDownload) throw IOException("cancelled")
                        val n = stream.read(buf)
                        if (n < 0) break
                        out.write(buf, 0, n)
                        digest.update(buf, 0, n)
                        received += n
                        reportProgress(received, total)
                    }
                }
            }
        }
        } catch (e: Exception) {
            part.delete()
            throw e
        }
        if (latest.sha256.isNotBlank()) {
            val hex = digest.digest().joinToString("") { "%02x".format(it) }
            if (!hex.equals(latest.sha256, ignoreCase = true)) {
                part.delete()
                throw IOException("sha256 mismatch")
            }
        }
        if (apk.exists()) apk.delete()
        if (!part.renameTo(apk)) {
            part.copyTo(apk, overwrite = true)
            part.delete()
        }
        return apk
    }

    private fun ensureCanInstall(apk: File) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
            !activity.packageManager.canRequestPackageInstalls()
        ) {
            showPermissionDialog(apk)
            return
        }
        install(apk)
    }

    private fun showPermissionDialog(apk: File) {
        if (activity.isFinishing || activity.isDestroyed) return
        if (permissionDialog?.isShowing == true) return
        pendingInstall = apk
        val dialog = dialog()
            .setTitle(R.string.upd_found)
            .setMessage(R.string.upd_need_permission)
            .setPositiveButton(R.string.upd_open_settings) { _, _ ->
                openInstallSettings()
            }
            .setNegativeButton(R.string.upd_later) { _, _ -> pendingInstall = null }
            .create()
        permissionDialog = dialog
        dialog.show()
    }

    private fun openInstallSettings() {
        runCatching {
            activity.startActivity(
                Intent(
                    Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:" + activity.packageName),
                ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            )
        }.onFailure {
            runCatching {
                activity.startActivity(
                    Intent(
                        Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                        Uri.parse("package:" + activity.packageName),
                    ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                )
            }
        }
    }

    private fun install(apk: File) {
        runCatching {
            val installer = activity.packageManager.packageInstaller
            val params = PackageInstaller.SessionParams(
                PackageInstaller.SessionParams.MODE_FULL_INSTALL,
            )
            val sessionId = installer.createSession(params)
            installer.openSession(sessionId).use { session ->
                apk.inputStream().use { input ->
                    session.openWrite("base.apk", 0, apk.length()).use { out ->
                        input.copyTo(out)
                        session.fsync(out)
                    }
                }
                val callback = Intent(activity, UpdateInstallReceiver::class.java)
                val flags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                    PendingIntent.FLAG_MUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
                } else {
                    PendingIntent.FLAG_UPDATE_CURRENT
                }
                val pending = PendingIntent.getBroadcast(activity, sessionId, callback, flags)
                session.commit(pending.intentSender)
            }
        }.onFailure {
            toast(R.string.upd_install_fail)
        }
    }

    private fun toast(resId: Int) {
        if (Looper.myLooper() == Looper.getMainLooper()) {
            Toast.makeText(activity, resId, Toast.LENGTH_LONG).show()
        } else {
            main.post { toast(resId) }
        }
    }

    companion object {
        private const val OPEN_DELAY_MS = 1200L
        private const val RETRY_DELAY_MS = 5000L
        private const val SILENT_RETRIES = 2
    }
}
