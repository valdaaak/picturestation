// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.ui.admin

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import org.picturestation.app.AppViewModel
import org.picturestation.app.R
import org.picturestation.app.data.AlbumProps
import org.picturestation.app.data.baseName
import org.picturestation.app.data.json
import org.picturestation.app.ui.Amber

/** The web's "Edit album": title, description, order of sub-albums, who may see it (private, public, with a
 *  password) and the cover photo. Saves with album_set and asks the lists behind to load again. */
@Composable
fun AlbumEditDialog(vm: AppViewModel, path: String, onDone: () -> Unit) {
    var props by remember { mutableStateOf<AlbumProps?>(null) }
    var title by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var order by remember { mutableStateOf("asc") }
    var mode by remember { mutableStateOf("private") }
    var password by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(path) {
        val p = vm.adminFetch { albumGet(path) }
        if (p == null) onDone() else { props = p; title = p.title; description = p.description; order = p.albumOrder; mode = p.mode }
    }
    val p = props ?: return
    val ctx = LocalContext.current
    val okSaved = stringResource(R.string.album_saved)
    val okCover = stringResource(R.string.cover_reset_done)
    val pwShort = stringResource(R.string.album_pw_min4)
    val busy = vm.admin?.busy == true
    AlertDialog(
        onDismissRequest = onDone,
        title = { Text(stringResource(R.string.album_fmt, baseName(path))) },
        text = {
            Column(modifier = Modifier.verticalScroll(rememberScrollState())) {
                FormField(stringResource(R.string.title_label), title, { title = it }, placeholder = baseName(path))
                Spacer(Modifier.height(8.dp))
                FormField(stringResource(R.string.album_description), description, { description = it }, singleLine = false)
                Spacer(Modifier.height(8.dp))
                OptionPicker(stringResource(R.string.album_order),
                    listOf("asc" to stringResource(R.string.order_asc), "desc" to stringResource(R.string.order_desc)), order) { order = it }
                Spacer(Modifier.height(8.dp))
                SectionTitle(stringResource(R.string.album_access_legend))
                RadioRow(stringResource(R.string.album_private), stringResource(R.string.album_private_hint), mode == "private") { mode = "private" }
                RadioRow(stringResource(R.string.album_public), stringResource(R.string.album_public_hint), mode == "public") { mode = "public" }
                RadioRow(stringResource(R.string.album_pw_mode), stringResource(R.string.album_pw_hint), mode == "password") { mode = "password" }
                if (mode == "password") FormField(stringResource(R.string.album_pw_label), password, { password = it }, password = true,
                    placeholder = stringResource(if (p.hasPassword) R.string.album_pw_keep else R.string.album_pw_min4))
                Spacer(Modifier.height(8.dp))
                val rights = (p.users + p.groups.map { ctx.getString(R.string.group_fmt, it) }).joinToString(", ")
                MutedText(stringResource(R.string.album_rights, rights.ifEmpty { stringResource(R.string.album_rights_nobody) }))
                if (p.excluded.isNotEmpty()) MutedText(stringResource(R.string.album_excluded_for, p.excluded.joinToString(", ")))
                val coverWhat = when {
                    p.cover.isNotEmpty() -> stringResource(R.string.cover_gallery)
                    p.eaCover.isNotEmpty() -> stringResource(R.string.cover_ea)
                    else -> stringResource(R.string.cover_first)
                }
                MutedText(stringResource(R.string.album_cover, coverWhat))
                if (p.cover.isNotEmpty()) TextButton(onClick = {
                    vm.adminRun("album_set", json("path" to path, "cover" to ""), ok = okCover, reload = false) { e ->
                        if (e == null) { vm.markBrowseStale(); onDone() } else error = e
                    }
                }) { Text(stringResource(R.string.cover_reset), color = Amber) }
                InlineError(error)
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    if (mode == "password" && !p.hasPassword && password.length < 4) { error = pwShort; return@TextButton }
                    if (mode == "password" && password.isNotEmpty() && password.length < 4) { error = pwShort; return@TextButton }
                    error = null
                    vm.adminRun("album_set", json("path" to path, "title" to title.trim(), "description" to description.trim(), "mode" to mode,
                        "album_order" to order, "password" to password.takeIf { mode == "password" && it.isNotEmpty() }), ok = okSaved, reload = false) { e ->
                        if (e == null) { vm.markBrowseStale(); onDone() } else error = e
                    }
                },
                enabled = !busy,
            ) { Text(stringResource(R.string.save)) }
        },
        dismissButton = { TextButton(onClick = onDone) { Text(stringResource(R.string.cancel)) } },
    )
}
