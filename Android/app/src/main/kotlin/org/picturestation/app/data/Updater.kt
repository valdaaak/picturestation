// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.data

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.net.Uri
import android.os.Build
import android.provider.Settings
import android.util.Log
import okhttp3.Request
import org.json.JSONObject
import java.io.File

/**
 * Updates from the gallery's own server: `/app/version.json` says which version is there
 * (`{"versionCode": 3, "versionName": "0.1.2", "apk": "Picturestation.apk"}`), the APK lies next to it.
 *
 * A newer version is downloaded to the cache and installed through a PackageInstaller session. On Android 12
 * and later an app may update itself without a confirmation (UPDATE_PACKAGES_WITHOUT_USER_ACTION, and the user
 * once allowed installs from this app): the app then replaces itself at the start; Android stops it and does not
 * let it start again from the background, so the user opens the new version. Where a confirmation is still
 * required the system's dialog appears; the first time Android asks to allow installs from this app.
 */
object Updater {
    private const val TAG = "Picturestation"
    const val ACTION_STATUS = "org.picturestation.app.UPDATE_STATUS"

    /** `sha256`: hex digest of the APK when version.json carries one (publish.py writes it); checked after the download. */
    data class Info(val versionCode: Int, val versionName: String, val apk: String, val sha256: String = "")

    /** Told what the installer answered: success, a failure message, or null when the user has to confirm. */
    @Volatile var onResult: ((success: Boolean, message: String?) -> Unit)? = null

    /** The version on the server, null when there is none or it cannot be read. */
    fun check(api: Api): Info? {
        if (api.server.isEmpty()) return null
        return try {
            api.client.newCall(Request.Builder().url(api.server + "/app/version.json").get().build()).execute().use { resp ->
                if (!resp.isSuccessful) return null
                if (!sameOrigin(resp, api)) return null
                val o = JSONObject(resp.body?.string() ?: "")
                Info(o.optInt("versionCode", 0), o.optString("versionName", ""), o.optString("apk", "Picturestation.apk"),
                    o.optString("sha256", "").lowercase())
            }
        } catch (e: Exception) {
            null
        }
    }

    fun canInstall(ctx: Context): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.O || ctx.packageManager.canRequestPackageInstalls()

    /** True when the update can go through without the user: Android 12+, installs from this app allowed, and the
     *  server reached over https (Android accepts only an APK signed with this app's key anyway; over plain http
     *  the user still gets the system's confirmation). */
    fun canInstallSilently(ctx: Context, api: Api): Boolean =
        Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && canInstall(ctx) && api.server.startsWith("https://")

    /** An APK larger than this is not an update of this app. */
    private const val MAX_APK_BYTES = 100L * 1024 * 1024

    /** The answer must come from the server's own scheme and host: a redirect elsewhere (https to http, another
     *  host) is not followed for update files. */
    private fun sameOrigin(resp: okhttp3.Response, api: Api): Boolean {
        val want = Uri.parse(api.server)
        val got = resp.request.url
        return got.scheme == want.scheme && got.host.equals(want.host, ignoreCase = true)
    }

    fun openInstallPermission(ctx: Context) {
        ctx.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${ctx.packageName}"))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    /** Downloads the APK into the cache; throws on failure. */
    fun download(ctx: Context, api: Api, info: Info): File {
        val name = File(info.apk).name.replace(Regex("[^A-Za-z0-9._-]"), "_").ifEmpty { "Picturestation.apk" }
        api.client.newCall(Request.Builder().url(api.server + "/app/" + name).get().build()).execute().use { resp ->
            if (!resp.isSuccessful) throw IllegalStateException("HTTP ${resp.code}")
            if (!sameOrigin(resp, api)) throw IllegalStateException("redirected away from the server")
            val dir = File(ctx.cacheDir, "update").apply { mkdirs() }
            val file = File(dir, "update.apk")
            val digest = java.security.MessageDigest.getInstance("SHA-256")
            var total = 0L
            resp.body!!.byteStream().use { input ->
                file.outputStream().use { out ->
                    val buf = ByteArray(64 * 1024)
                    while (true) {
                        val n = input.read(buf); if (n < 0) break
                        total += n
                        if (total > MAX_APK_BYTES) { file.delete(); throw IllegalStateException("APK too large") }
                        out.write(buf, 0, n); digest.update(buf, 0, n)
                    }
                }
            }
            val sum = digest.digest().joinToString("") { "%02x".format(it) }
            if (info.sha256.isNotEmpty() && sum != info.sha256) { file.delete(); throw IllegalStateException("APK checksum mismatch") }
            return file
        }
    }

    /** Installs the downloaded APK over this app; the answer comes to [onResult] through [UpdateReceiver].
     *  `silent`: ask Android to skip its confirmation (only when [canInstallSilently] said so). */
    fun install(ctx: Context, file: File, silent: Boolean) {
        val installer = ctx.packageManager.packageInstaller
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
        params.setAppPackageName(ctx.packageName)
        if (silent && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S)
            params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED)
        val id = installer.createSession(params)
        installer.openSession(id).use { session ->
            session.openWrite("Picturestation.apk", 0, file.length()).use { out ->
                file.inputStream().use { it.copyTo(out) }
                session.fsync(out)
            }
            val intent = Intent(ctx, UpdateReceiver::class.java).setAction(ACTION_STATUS)
            val flags = PendingIntent.FLAG_UPDATE_CURRENT or
                (if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) PendingIntent.FLAG_MUTABLE else 0)
            session.commit(PendingIntent.getBroadcast(ctx, id, intent, flags).intentSender)
        }
        Log.i(TAG, "update session $id committed")
    }
}

/** The installer's answer to a session: a confirmation to show, success (the app is about to be replaced) or a failure. */
class UpdateReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        val status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)
        val message = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE)
        Log.i("Picturestation", "update status $status $message")
        when (status) {
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                @Suppress("DEPRECATION")
                val confirm = intent.getParcelableExtra<Intent>(Intent.EXTRA_INTENT) ?: return
                ctx.startActivity(confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                Updater.onResult?.invoke(false, null)
            }
            PackageInstaller.STATUS_SUCCESS -> Updater.onResult?.invoke(true, null)
            else -> Updater.onResult?.invoke(false, message ?: "status $status")
        }
    }
}
