// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.data

import android.net.Uri
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Locale

/**
 * The administration API of a gallery (`/api/admin/{op}`, server/picturestation/admin.py), the same one the web
 * gallery's Settings use. The session travels in the X-SYNO-TOKEN header (the client's interceptor), the server
 * answers 401 when it is gone and 403 when the user is no administrator; errors come as `{"error": message}` in
 * the language asked for with X-Lang.
 */
class AdminApi(private val api: Api) {
    private val lang: String get() = if (Locale.getDefault().language in listOf("sk", "cs")) "sk" else "en"
    private fun url(op: String) = api.server + "/api/admin/" + op

    private fun handle(resp: Response): JSONObject {
        val text = resp.body?.string() ?: ""
        val j = try { JSONObject(text) } catch (e: Exception) { throw Api.ApiException(Api.Kind.BAD, resp.code) }
        if (resp.code == 401) throw Api.ApiException(Api.Kind.SESSION, 401, j.optString("error"))
        if (resp.code >= 400) throw Api.ApiException(Api.Kind.API, resp.code, j.optString("error", "HTTP ${resp.code}"))
        return j
    }

    suspend fun get(op: String, params: Map<String, String> = emptyMap()): JSONObject = withContext(Dispatchers.IO) {
        val u = Uri.parse(url(op)).buildUpon().also { b -> params.forEach { (k, v) -> b.appendQueryParameter(k, v) } }.build().toString()
        val req = Request.Builder().url(u).get().header("X-Lang", lang).build()
        val resp = try { api.client.newCall(req).execute() } catch (e: IOException) { throw Api.ApiException(Api.Kind.NETWORK) }
        resp.use { handle(it) }
    }

    suspend fun post(op: String, body: JSONObject): JSONObject = withContext(Dispatchers.IO) {
        val req = Request.Builder().url(url(op))
            .post(body.toString().toRequestBody("application/json; charset=utf-8".toMediaType()))
            .header("X-Lang", lang).build()
        val resp = try { api.client.newCall(req).execute() } catch (e: IOException) { throw Api.ApiException(Api.Kind.NETWORK) }
        resp.use { handle(it) }
    }

    // ---------- readers ----------
    suspend fun state(): AdminInfo = parseInfo(get("state"))
    suspend fun albums(path: String): AlbumsList = get("albums", mapOf("path" to path)).let {
        AlbumsList(it.optString("path"), it.optJSONArray("albums").strings(), it.optInt("files"))
    }
    suspend fun albumGet(path: String): AlbumProps = get("album_get", mapOf("path" to path)).let { o ->
        AlbumProps(o.optString("path"), o.optString("title"), o.optString("description"), o.optString("cover"),
            o.optString("ea_cover"), o.optString("mode", "private"), o.optBoolean("has_password"),
            o.optString("album_order", "asc"), o.optJSONArray("users").strings(), o.optJSONArray("groups").strings(),
            o.optJSONArray("excluded").strings())
    }
    suspend fun accessView(type: String, name: String, path: String): AccessView =
        post("access_view", json("type" to type, "name" to name, "path" to path)).let { o ->
            AccessView(o.optString("path"), parseState(o.optJSONObject("self")), o.optInt("files"),
                o.optJSONArray("albums").objects().map { AccessRow(it.optString("name"), it.optString("path"), parseState(it)) })
        }
    suspend fun albumAccess(path: String): AlbumAccess = post("album_access", json("path" to path)).let { o ->
        AlbumAccess(o.optString("path"), o.optJSONArray("principals").objects().map {
            Principal(it.optString("type"), it.optString("name"), it.optBoolean("disabled"), parseState(it))
        })
    }
    suspend fun shareList(): List<Share> = get("share_list").optJSONArray("shares").objects().map { o ->
        Share(o.optString("token"), o.optString("path"), o.optString("kind"), o.optString("created_by"), o.optLong("created"),
            if (o.isNull("expires")) null else o.optLong("expires"), o.optBoolean("expired"), o.optBoolean("allow_download"), o.optString("note"))
    }
    suspend fun deviceList(): List<Device> = get("device_list").optJSONArray("devices").objects().map { o ->
        Device(o.optInt("id"), o.optString("name"), o.optString("username"), o.optLong("created"),
            if (o.isNull("last_seen")) null else o.optLong("last_seen"))
    }
    suspend fun tagNames(): List<String> = get("tag_names").optJSONArray("tags").strings()
    suspend fun movesState(): MovesState = get("moves_state").let { o ->
        MovesState(
            o.optJSONArray("history").objects().map { MoveHist(it.optString("old"), it.optString("new"), it.optString("kind"), it.optLong("created")) },
            o.optJSONArray("pending").objects().map { MovePending(it.optString("old"), it.optJSONArray("candidates").strings(), it.optLong("created")) },
            o.optJSONArray("orphans").objects().map { Orphan(it.optString("path"), it.optInt("rules"), it.optBoolean("props"), it.optInt("shares"), it.optInt("smart"), it.optInt("nested")) },
        )
    }
    suspend fun galleriesList(): GalleriesList = get("galleries_list").let { o ->
        GalleriesList(o.optJSONArray("galleries").objects().map { g ->
            PrivateGallery(g.optString("name"), g.optString("title"), g.optString("root"), g.optJSONArray("hostnames").strings(),
                g.optBoolean("enabled", true), g.optLong("created"), g.optBoolean("root_ok", true),
                if (g.isNull("files")) null else g.optInt("files"), g.optJSONArray("admins").strings(), g.optString("path"))
        }, o.optJSONArray("roots").strings())
    }

    // ---------- writers used from several places ----------
    suspend fun grant(type: String, name: String, path: String, deny: Boolean = false, clearBelow: Boolean = false) {
        post("grant", json("type" to type, "name" to name, "path" to path, "deny" to deny, "clear_below" to clearBelow))
    }
    suspend fun revoke(type: String, name: String, path: String) {
        post("revoke", json("type" to type, "name" to name, "path" to path))
    }
    /** Creates a share link; returns its token. */
    suspend fun shareCreate(path: String, days: Int, allowDownload: Boolean, note: String): String =
        post("share_create", json("path" to path, "days" to days, "allow_download" to allowDownload, "note" to note)).optString("token")

    private fun parseInfo(o: JSONObject): AdminInfo {
        val s = o.optJSONObject("settings") ?: JSONObject()
        return AdminInfo(
            version = o.optString("version"), isMain = o.optBoolean("is_main"),
            users = o.optJSONArray("users").objects().map { u ->
                AdminUser(u.optString("username"), u.optBoolean("admin"), u.optBoolean("disabled"), u.optString("note"),
                    parseGrants(u.optJSONArray("grants")), u.optJSONArray("groups").strings())
            },
            groups = o.optJSONArray("groups").objects().map { g ->
                AdminGroup(g.optString("name"), g.optString("note"), g.optJSONArray("members").strings(), parseGrants(g.optJSONArray("grants")))
            },
            guestGrants = parseGrants(o.optJSONObject("guest")?.optJSONArray("grants")),
            settings = AdminSettings(s.optString("title"), s.optString("root_album_order", "asc"), s.optString("language", "auto"),
                FLAG_KEYS.associateWith { s.optBoolean(it) }),
        )
    }
    private fun parseGrants(arr: JSONArray?) = arr.objects().map { Grant(it.optString("path"), it.optBoolean("deny")) }
    private fun parseState(o: JSONObject?): AccessState {
        o ?: return AccessState(null, "no", null, emptyList())
        val v = o.optJSONObject("via")
        val via = v?.let { Via(it.optBoolean("admin"), it.optBoolean("deny"), it.optString("path"), it.optJSONArray("groups").strings()) }
        return AccessState(if (o.isNull("rule")) null else o.optString("rule"), o.optString("effective", "no"), via, o.optJSONArray("below").strings())
    }
}

/** The twelve restriction flags of a gallery, in the web's order; none of them applies to administrators. */
val FLAG_KEYS = listOf("allow_download_user", "allow_download_guest", "hide_gps", "hide_detail_user", "hide_detail_guest",
    "disable_timeline", "disable_search", "allow_comment_user", "allow_comment_guest", "root_files_public", "people_for_guest", "live_photos")

data class Grant(val path: String, val deny: Boolean)
data class AdminUser(val username: String, val admin: Boolean, val disabled: Boolean, val note: String, val grants: List<Grant>, val groups: List<String>)
data class AdminGroup(val name: String, val note: String, val members: List<String>, val grants: List<Grant>)
data class AdminSettings(val title: String, val rootAlbumOrder: String, val language: String, val flags: Map<String, Boolean>)
data class AdminInfo(val version: String, val isMain: Boolean, val users: List<AdminUser>, val groups: List<AdminGroup>,
                     val guestGrants: List<Grant>, val settings: AdminSettings)
/** Where an inherited rule comes from: an admin sees everything, or a rule on `path` (maybe through groups). */
data class Via(val admin: Boolean, val deny: Boolean, val path: String, val groups: List<String>)
/** rule: allow | deny | null (own rule on this path); effective: all | yes | path | no; below: own rules under this path. */
data class AccessState(val rule: String?, val effective: String, val via: Via?, val below: List<String>)
data class AccessRow(val name: String, val path: String, val state: AccessState)
data class AccessView(val path: String, val self: AccessState, val files: Int, val albums: List<AccessRow>)
data class Principal(val type: String, val name: String, val disabled: Boolean, val state: AccessState)
data class AlbumAccess(val path: String, val principals: List<Principal>)
data class AlbumsList(val path: String, val albums: List<String>, val files: Int)
data class AlbumProps(val path: String, val title: String, val description: String, val cover: String, val eaCover: String,
                      val mode: String, val hasPassword: Boolean, val albumOrder: String, val users: List<String>,
                      val groups: List<String>, val excluded: List<String>)
data class Share(val token: String, val path: String, val kind: String, val createdBy: String, val created: Long, val expires: Long?,
                 val expired: Boolean, val allowDownload: Boolean, val note: String)
data class Device(val id: Int, val name: String, val username: String, val created: Long, val lastSeen: Long?)
data class PrivateGallery(val name: String, val title: String, val root: String, val hostnames: List<String>, val enabled: Boolean,
                          val created: Long, val rootOk: Boolean, val files: Int?, val admins: List<String>, val path: String)
data class GalleriesList(val galleries: List<PrivateGallery>, val roots: List<String>)
data class MoveHist(val old: String, val new: String, val kind: String, val created: Long)
data class MovePending(val old: String, val candidates: List<String>, val created: Long)
data class Orphan(val path: String, val rules: Int, val props: Boolean, val shares: Int, val smart: Int, val nested: Int)
data class MovesState(val history: List<MoveHist>, val pending: List<MovePending>, val orphans: List<Orphan>)

// ---------- helpers ----------
/** A JSON object from pairs; nulls are left out, lists become arrays. */
fun json(vararg pairs: Pair<String, Any?>): JSONObject {
    val o = JSONObject()
    for ((k, v) in pairs) {
        when (v) {
            null -> {}
            is List<*> -> o.put(k, JSONArray().also { a -> v.forEach { a.put(it) } })
            else -> o.put(k, v)
        }
    }
    return o
}

fun JSONArray?.strings(): List<String> {
    this ?: return emptyList()
    return (0 until length()).map { optString(it) }
}

fun JSONArray?.objects(): List<JSONObject> {
    this ?: return emptyList()
    return (0 until length()).mapNotNull { optJSONObject(it) }
}

/** The relative path hidden in a DS photo id: `album_<hex>` or `photo|video_<hex dir>_<hex name>` (server ids.py). */
fun decodeIdPath(id: String): String? {
    fun hex(s: String): String? = try {
        if (s.isEmpty() || s.length % 2 != 0) null
        else String(s.chunked(2).map { it.toInt(16).toByte() }.toByteArray(), Charsets.UTF_8)
    } catch (e: Exception) { null }
    return when {
        id.startsWith("album_") -> hex(id.removePrefix("album_"))
        id.startsWith("photo_") || id.startsWith("video_") -> {
            val parts = id.substringAfter('_').split('_')
            if (parts.size != 2) return null
            val dir = hex(parts[0]) ?: return null
            val name = hex(parts[1]) ?: return null
            if (dir == "/" || dir.isEmpty()) name else "$dir/$name"
        }
        else -> null
    }
}

fun baseName(path: String): String = path.substringAfterLast('/')

/** The albums a file or album lies in, nearest first: "2024/Trip/IMG.jpg" -> ["2024/Trip", "2024"]. */
fun parentAlbums(rel: String): List<String> {
    val parts = rel.split('/').dropLast(1)
    return (parts.size downTo 1).map { parts.take(it).joinToString("/") }
}

fun shareUrl(base: String, token: String) = "$base/s/$token"

/** A day from Unix seconds in the device's format, e.g. "20. 5. 2023" or "May 20, 2023". */
fun fmtDay(epoch: Long): String =
    Instant.ofEpochSecond(epoch).atZone(ZoneId.systemDefault()).toLocalDate().format(DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM))
