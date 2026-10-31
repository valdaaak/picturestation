// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.data

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/** What the app remembers: the server, the device session (encrypted with the Android Keystore) and preferences.
 *  When the encrypted storage is not available, the session is kept in memory only (a new code after a restart);
 *  it is never written in the clear. */
class Store(ctx: Context) {
    private val plain: SharedPreferences = ctx.getSharedPreferences("picturestation", Context.MODE_PRIVATE)
    private val secure: SharedPreferences? = try {
        val key = MasterKey.Builder(ctx).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build()
        EncryptedSharedPreferences.create(
            ctx, "picturestation_secure", key,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    } catch (e: Exception) {
        null
    }
    private var memorySid = ""
    val sessionPersists: Boolean get() = secure != null
    private val prefs: SharedPreferences get() = plain

    var server: String
        get() = prefs.getString("server", "") ?: ""
        set(v) = prefs.edit().putString("server", v).apply()

    var sid: String
        get() = secure?.getString("sid", "") ?: memorySid
        set(v) { if (secure != null) secure.edit().putString("sid", v).apply() else memorySid = v }

    var user: String
        get() = prefs.getString("user", "") ?: ""
        set(v) = prefs.edit().putString("user", v).apply()

    var title: String
        get() = prefs.getString("title", "") ?: ""
        set(v) = prefs.edit().putString("title", v).apply()

    /** Seconds between photos of a slideshow. */
    var interval: Int
        get() = prefs.getInt("interval", 8)
        set(v) = prefs.edit().putInt("interval", v).apply()
}
