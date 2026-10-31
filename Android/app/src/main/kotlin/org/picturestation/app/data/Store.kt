// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.data

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/** What the app remembers: the server, the device session (encrypted with the Android Keystore) and preferences. */
class Store(ctx: Context) {
    private val prefs: SharedPreferences = try {
        val key = MasterKey.Builder(ctx).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build()
        EncryptedSharedPreferences.create(
            ctx, "picturestation", key,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    } catch (e: Exception) {
        ctx.getSharedPreferences("picturestation_plain", Context.MODE_PRIVATE)
    }

    var server: String
        get() = prefs.getString("server", "") ?: ""
        set(v) = prefs.edit().putString("server", v).apply()

    var sid: String
        get() = prefs.getString("sid", "") ?: ""
        set(v) = prefs.edit().putString("sid", v).apply()

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
