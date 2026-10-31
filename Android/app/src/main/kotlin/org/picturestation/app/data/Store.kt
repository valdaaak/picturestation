// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.data

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import org.json.JSONArray
import org.json.JSONObject

/** What the app remembers: the paired galleries (each with its own device session, encrypted with the Android
 *  Keystore), which of them is active, and preferences. When the encrypted storage is not available, the sessions
 *  are kept in memory only (a new code after a restart); they are never written in the clear.
 *
 *  A gallery is one base URL: the main gallery of a server (`https://photos.example.com`) or a private one on it
 *  (`https://photos.example.com/~name`). Each is paired on its own, with a code approved in that gallery. */
class Store(ctx: Context) {
    data class Gallery(val base: String, val user: String, val title: String)

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
    private val memorySids = HashMap<String, String>()
    val sessionPersists: Boolean get() = secure != null

    init { migrate() }

    /** Versions up to 0.1.3 kept one server in `server`/`user`/`title` and its session in `sid`. */
    private fun migrate() {
        if (plain.contains("galleries")) return
        val server = plain.getString("server", "") ?: ""
        if (server.isNotEmpty()) {
            galleries = listOf(Gallery(server, plain.getString("user", "") ?: "", plain.getString("title", "") ?: ""))
            active = 0
            val sid = secure?.getString("sid", "") ?: ""
            if (sid.isNotEmpty()) setSid(server, sid)
        }
        plain.edit().remove("server").remove("user").remove("title").apply()
        secure?.edit()?.remove("sid")?.apply()
    }

    var galleries: List<Gallery>
        get() = try {
            val arr = JSONArray(plain.getString("galleries", "[]") ?: "[]")
            (0 until arr.length()).map { arr.getJSONObject(it) }
                .map { Gallery(it.optString("base"), it.optString("user"), it.optString("title")) }
                .filter { it.base.isNotEmpty() }
        } catch (e: Exception) { emptyList() }
        set(v) {
            val arr = JSONArray()
            v.forEach { arr.put(JSONObject().put("base", it.base).put("user", it.user).put("title", it.title)) }
            plain.edit().putString("galleries", arr.toString()).apply()
        }

    /** Index of the active gallery, always within the list. */
    var active: Int
        get() = plain.getInt("active", 0).coerceIn(0, maxOf(0, galleries.size - 1))
        set(v) = plain.edit().putInt("active", v).apply()

    val current: Gallery? get() = galleries.getOrNull(active)

    /** The active gallery's base URL and session; "" when there is none. */
    val server: String get() = current?.base ?: ""
    val sid: String get() = current?.let { sidOf(it.base) } ?: ""

    fun sidOf(base: String): String = secure?.getString("sid:$base", "") ?: memorySids[base] ?: ""

    /** Stores the session of a gallery; an empty one forgets it. */
    fun setSid(base: String, sid: String) {
        if (secure != null) {
            if (sid.isEmpty()) secure.edit().remove("sid:$base").apply() else secure.edit().putString("sid:$base", sid).apply()
        } else if (sid.isEmpty()) memorySids.remove(base) else memorySids[base] = sid
    }

    /** Adds a gallery or replaces the one with the same base; returns its index. */
    fun upsert(g: Gallery): Int {
        val list = galleries.toMutableList()
        val i = list.indexOfFirst { it.base == g.base }
        if (i >= 0) list[i] = g else list.add(g)
        galleries = list
        return if (i >= 0) i else list.size - 1
    }

    /** Forgets a gallery and its session; the active index follows the remaining list. */
    fun remove(i: Int) {
        val list = galleries.toMutableList()
        val g = list.getOrNull(i) ?: return
        list.removeAt(i)
        setSid(g.base, "")
        val a = plain.getInt("active", 0)
        galleries = list
        active = when {
            a > i -> a - 1
            a == i -> a.coerceAtMost(maxOf(0, list.size - 1))
            else -> a
        }
    }

    /** Seconds between photos of a slideshow. */
    var interval: Int
        get() = plain.getInt("interval", 8)
        set(v) = plain.edit().putInt("interval", v).apply()
}
