// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.data

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import okhttp3.Request
import org.json.JSONObject
import java.io.File

/**
 * Updates from the gallery's own server: `/app/version.json` says which version is there
 * (`{"versionCode": 3, "versionName": "0.1.2", "apk": "Picturestation.apk"}`), the APK lies next to it.
 * A newer version is downloaded to the cache and handed to the system installer; the first time Android asks
 * to allow installs from this app.
 */
object Updater {
    data class Info(val versionCode: Int, val versionName: String, val apk: String)

    /** The version on the server, null when there is none or it cannot be read. */
    fun check(api: Api): Info? {
        if (api.server.isEmpty()) return null
        return try {
            api.client.newCall(Request.Builder().url(api.server + "/app/version.json").get().build()).execute().use { resp ->
                if (!resp.isSuccessful) return null
                val o = JSONObject(resp.body?.string() ?: "")
                Info(o.optInt("versionCode", 0), o.optString("versionName", ""), o.optString("apk", "Picturestation.apk"))
            }
        } catch (e: Exception) {
            null
        }
    }

    fun canInstall(ctx: Context): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.O || ctx.packageManager.canRequestPackageInstalls()

    fun openInstallPermission(ctx: Context) {
        ctx.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${ctx.packageName}"))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    /** Downloads the APK into the cache; throws on failure. */
    fun download(ctx: Context, api: Api, info: Info): File {
        val name = File(info.apk).name.replace(Regex("[^A-Za-z0-9._-]"), "_").ifEmpty { "Picturestation.apk" }
        api.client.newCall(Request.Builder().url(api.server + "/app/" + name).get().build()).execute().use { resp ->
            if (!resp.isSuccessful) throw IllegalStateException("HTTP ${resp.code}")
            val dir = File(ctx.cacheDir, "update").apply { mkdirs() }
            val file = File(dir, "update.apk")
            resp.body!!.byteStream().use { input -> file.outputStream().use { out -> input.copyTo(out) } }
            return file
        }
    }

    fun install(ctx: Context, file: File) {
        val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.fileprovider", file)
        ctx.startActivity(Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        })
    }
}
