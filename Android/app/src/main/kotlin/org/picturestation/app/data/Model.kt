// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.data

import org.json.JSONArray
import org.json.JSONObject

/** One entry of a list: an album, a photo or a video (the DS photo API's BasicItem, see docs/protocol.md). */
data class Item(
    val id: String,
    val type: String,            // album | photo | video
    val name: String,
    val title: String,
    val taken: String?,          // "YYYY-MM-DD HH:MM:SS"
    val hasThumb: Boolean,
    val thumbMtime: String?,
    val sig: String?,            // album cover signature
    val durationMs: Int,
    val rotation: Int?,          // video: 0/90/180/270, null = not known yet
    val tvVersion: String?,      // video: none | ready | waiting | unknown
    val place: String?,
    val people: List<String>,
) {
    val isMedia get() = type == "photo" || type == "video"
}

fun parseItem(o: JSONObject): Item {
    val info = o.optJSONObject("info") ?: JSONObject()
    val add = o.optJSONObject("additional") ?: JSONObject()
    val ts = add.optJSONObject("thumb_size")
    val vc = add.optJSONObject("video_codec")
    val name = info.optString("name", o.optString("name", ""))
    val people = ArrayList<String>()
    info.optJSONArray("people")?.let { arr ->
        for (i in 0 until arr.length()) arr.optJSONObject(i)?.optString("name")?.takeIf { it.isNotEmpty() }?.let(people::add)
    }
    return Item(
        id = o.optString("id"),
        type = o.optString("type", "photo"),
        name = name,
        title = info.optString("title", "").ifEmpty { name },
        taken = info.optString("takendate", "").ifEmpty { null },
        hasThumb = o.optString("thumbnail_status", "default") != "default",
        thumbMtime = ts?.optJSONObject("small")?.optString("mtime", "")?.ifEmpty { null },
        sig = ts?.optString("sig", "")?.ifEmpty { null },
        durationMs = info.optString("duration", "0").toIntOrNull() ?: 0,
        rotation = if (vc != null && !vc.isNull("rotation")) vc.optInt("rotation") else null,
        tvVersion = vc?.optString("tv_version", "")?.ifEmpty { null },
        place = info.optString("place", "").ifEmpty { null },
        people = people,
    )
}

fun parseItems(arr: JSONArray?): List<Item> {
    val out = ArrayList<Item>()
    if (arr == null) return out
    for (i in 0 until arr.length()) arr.optJSONObject(i)?.let { out.add(parseItem(it)) }
    return out
}

/** "2023-05-20 14:03:00" -> "20. 5. 2023 14:03" (Slovak) or "20 May 2023 14:03". */
fun formatTaken(taken: String?, slovak: Boolean, noDate: String): String {
    val m = Regex("""^(\d{4})-(\d\d)-(\d\d)(?: (\d\d):(\d\d))?""").find(taken ?: "") ?: return noDate
    val (y, mo, d) = m.destructured.toList().take(3)
    val time = if (m.groupValues[4].isNotEmpty()) " ${m.groupValues[4]}:${m.groupValues[5]}" else ""
    val month = mo.toInt()
    return if (slovak) "${d.toInt()}. $month. $y$time"
    else "${d.toInt()} ${MONTHS_EN[month - 1]} $y$time"
}

private val MONTHS_EN = listOf("January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December")
