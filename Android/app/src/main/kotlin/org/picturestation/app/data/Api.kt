// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.data

import android.net.Uri
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.FormBody
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * Talks to Picturestation: the DS photo API (docs/protocol.md) and the pairing endpoints /api/tv/code and /api/tv/poll.
 * The session travels like the DS photo app's: X-SYNO-TOKEN header on calls, PHPSESSID in image and
 * video URLs. OkHttp's user agent has no "Mozilla", so the server treats us as an app.
 */
class Api(private val store: Store) {
    enum class Kind { NETWORK, BAD, SESSION, API }
    class ApiException(val kind: Kind, val code: Int = 0, msg: String = kind.name) : Exception(msg)

    val server: String get() = store.server
    val sid: String get() = store.sid

    /** The one HTTP client of the app: it adds the session header to every request that goes to the
     *  configured server (API calls, thumbnails through Coil, videos through Media3), and to nothing else. */
    val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS).readTimeout(40, TimeUnit.SECONDS)
        .addInterceptor { chain ->
            val req = chain.request()
            val host = Uri.parse(server).host
            if (sid.isNotEmpty() && host != null && req.url.host.equals(host, ignoreCase = true))
                chain.proceed(req.newBuilder().header("X-SYNO-TOKEN", sid).build())
            else chain.proceed(req)
        }.build()

    /** POST form to `path` on `base` (default: the saved server). Returns the JSON body. */
    suspend fun post(path: String, params: Map<String, String>, base: String = server): JSONObject =
        withContext(Dispatchers.IO) {
            val form = FormBody.Builder().also { b -> params.forEach { (k, v) -> b.add(k, v) } }.build()
            val req = Request.Builder().url(base + path).post(form).build()
            val resp = try { client.newCall(req).execute() } catch (e: IOException) { throw ApiException(Kind.NETWORK) }
            resp.use {
                val text = it.body?.string() ?: ""
                if (it.header("x-request-error") == "error_timeout") throw ApiException(Kind.SESSION)
                val j = try { JSONObject(text) } catch (e: Exception) { throw ApiException(Kind.BAD, it.code) }
                if (it.code >= 400) throw ApiException(Kind.BAD, it.code, j.optString("error", "HTTP ${it.code}"))
                j
            }
        }

    /** DS photo API call; returns `data`. */
    suspend fun call(script: String, api: String, method: String, params: Map<String, String> = emptyMap(),
                     base: String = server): JSONObject {
        val p = HashMap<String, String>(params)
        p["api"] = api; p["method"] = method; p["version"] = "1"
        val j = post("/photo/webapi/$script", p, base)
        if (!j.optBoolean("success")) throw ApiException(Kind.API, j.optJSONObject("error")?.optInt("code") ?: 0)
        return j.optJSONObject("data") ?: j.optJSONArray("data")?.let { JSONObject().put("items", it) } ?: JSONObject()
    }

    /** True when `base` answers like Picturestation / Photo Station. */
    suspend fun isServer(base: String): Boolean {
        val d = call("query.php", "SYNO.API.Info", "query", mapOf("query" to "all"), base)
        return d.has("SYNO.PhotoStation.Auth")
    }

    suspend fun pairCode(deviceName: String): JSONObject = post("/api/tv/code", mapOf("name" to deviceName))
    suspend fun pairPoll(token: String): JSONObject = post("/api/tv/poll", mapOf("token" to token))

    suspend fun info(): JSONObject = call("info.php", "SYNO.PhotoStation.Info", "getinfo")

    /** The user of the session, "" when the session is gone. */
    suspend fun checkAuth(): String = call("auth.php", "SYNO.PhotoStation.Auth", "checkauth").optString("username", "")

    suspend fun logout() { runCatching { call("auth.php", "SYNO.PhotoStation.Auth", "logout") } }

    /** Albums and items of an album (null = the root). Returns the items and the total. */
    suspend fun listAlbum(albumId: String?, offset: Int, limit: Int, sortBy: String, sortDir: String): Pair<List<Item>, Int> {
        val p = hashMapOf("type" to "album,photo,video", "offset" to "$offset", "limit" to "$limit",
            "sort_by" to sortBy, "sort_direction" to sortDir, "additional" to "thumb_size,video_codec")
        if (albumId != null) p["id"] = albumId
        val d = call("album.php", "SYNO.PhotoStation.Album", "list", p)
        return parseItems(d.optJSONArray("items")) to d.optInt("total", 0)
    }

    /** Newest photos and videos of the whole gallery. */
    suspend fun listLatest(offset: Int, limit: Int): Pair<List<Item>, Int> {
        val d = call("photo.php", "SYNO.PhotoStation.Photo", "list", mapOf("type" to "photo,video",
            "offset" to "$offset", "limit" to "$limit", "sort_by" to "takendate", "sort_direction" to "desc",
            "additional" to "thumb_size,video_codec"))
        return parseItems(d.optJSONArray("items")) to d.optInt("total", 0)
    }

    /** One item with its people and place. */
    suspend fun details(id: String): Item? {
        val d = call("photo.php", "SYNO.PhotoStation.Photo", "getinfo", mapOf("id" to id, "additional" to "tags,video_codec,thumb_size"))
        return parseItems(d.optJSONArray("items")).firstOrNull()
    }

    /** URLs carry no session: the client's interceptor sends it in a header. */
    private fun withSid(u: Uri.Builder): String = u.build().toString()

    /** Thumbnail URL: size small (320 px), large (1280 px) or preview (160 px). */
    fun thumbUrl(item: Item, size: String): String {
        val u = Uri.parse("$server/photo/webapi/thumb.php").buildUpon()
            .appendQueryParameter("api", "SYNO.PhotoStation.Thumb").appendQueryParameter("method", "get")
            .appendQueryParameter("version", "1").appendQueryParameter("id", item.id).appendQueryParameter("size", size)
        item.thumbMtime?.let { u.appendQueryParameter("mtime", it) }
        item.sig?.let { u.appendQueryParameter("sig", it) }
        return withSid(u)
    }

    /** Video URL. `variant` "web" = the original or the NAS conversion (players honour the rotation flag);
     *  "tv" = additionally an upright copy for players that do not. */
    fun videoUrl(item: Item, variant: String = "web"): String {
        val u = Uri.parse("$server/photo/webapi/download.php").buildUpon()
            .appendQueryParameter("api", "SYNO.PhotoStation.Download").appendQueryParameter("method", "getvideo")
            .appendQueryParameter("version", "1").appendQueryParameter("id", item.id).appendQueryParameter("variant", variant)
        return withSid(u)
    }

    /** The original photo file. */
    fun originalUrl(item: Item): String {
        val u = Uri.parse("$server/photo/webapi/download.php").buildUpon()
            .appendQueryParameter("api", "SYNO.PhotoStation.Download").appendQueryParameter("method", "getphoto")
            .appendQueryParameter("version", "1").appendQueryParameter("id", item.id).appendQueryParameter("size", "original")
        return withSid(u)
    }

    companion object {
        /** "photos.example.com/" -> "https://photos.example.com"; a typed scheme is kept. Plain http is never
         *  tried on its own: the user has to ask for it (see SetupScreen), so that nobody on the way can
         *  downgrade the connection. */
        fun normalize(typed: String): String? {
            val s = typed.trim().trimEnd('/')
            if (s.isEmpty()) return null
            if (s.startsWith("http://") || s.startsWith("https://")) return s
            return "https://" + s.trimStart('/')
        }
    }
}
