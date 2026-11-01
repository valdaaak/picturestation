// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.ui.admin

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
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
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import org.picturestation.app.AppViewModel
import org.picturestation.app.R
import org.picturestation.app.data.Item
import org.picturestation.app.data.baseName
import org.picturestation.app.data.json
import org.picturestation.app.data.parentAlbums
import org.picturestation.app.ui.Amber

/** Makes the photo the cover of its album; a photo deeper in the tree may be the cover of any album above it. */
@Composable
fun CoverDialog(vm: AppViewModel, rel: String, onDone: () -> Unit) {
    val albums = remember(rel) { parentAlbums(rel) }
    val ctx = LocalContext.current
    val rootNote = stringResource(R.string.cover_root)
    fun set(album: String) {
        vm.adminRun("album_set", json("path" to album, "cover" to rel), ok = ctx.getString(R.string.cover_done, baseName(album)), reload = false) { e ->
            if (e == null) vm.markBrowseStale()
            onDone()
        }
    }
    LaunchedEffect(rel) {
        if (albums.isEmpty()) { vm.message = rootNote; onDone() }
        else if (albums.size == 1) set(albums[0])
    }
    if (albums.size < 2) return
    AlertDialog(
        onDismissRequest = onDone,
        title = { Text(stringResource(R.string.cover_title)) },
        text = {
            Column(modifier = Modifier.verticalScroll(rememberScrollState())) {
                MutedText(stringResource(R.string.cover_hint))
                Spacer(Modifier.height(6.dp))
                albums.forEachIndexed { i, a ->
                    TextButton(onClick = { set(a) }, contentPadding = PaddingValues(horizontal = 4.dp)) {
                        Text(a + (if (i == 0) " (" + stringResource(R.string.cover_this) + ")" else ""), color = Amber)
                    }
                }
            }
        },
        confirmButton = {},
        dismissButton = { TextButton(onClick = onDone) { Text(stringResource(R.string.cancel)) } },
    )
}

/** The description tags of a photo or video: remove with a cross, add by name (with the gallery's names offered). */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun TagsDialog(vm: AppViewModel, item: Item, onDone: () -> Unit) {
    var tags by remember { mutableStateOf<List<Pair<String, String>>?>(null) }
    var names by remember { mutableStateOf<List<String>>(emptyList()) }
    var text by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val okAdded = stringResource(R.string.tag_added)
    val okRemoved = stringResource(R.string.tag_removed)
    suspend fun reload() {
        vm.forgetDetails(item.id)
        tags = vm.details(item)?.tags ?: emptyList()
    }
    LaunchedEffect(item.id) {
        reload()
        names = vm.adminFetch { tagNames() } ?: emptyList()
    }
    fun add(name: String) {
        if (name.isBlank()) return
        vm.adminRun("tag_add", json("path" to item.path, "name" to name.trim()), ok = okAdded, reload = false) { e ->
            if (e == null) { text = ""; scope.launch { reload() } } else error = e
        }
    }
    AlertDialog(
        onDismissRequest = onDone,
        title = { Text(stringResource(R.string.tags)) },
        text = {
            Column(modifier = Modifier.verticalScroll(rememberScrollState())) {
                val t = tags
                when {
                    t == null -> Spinner()
                    t.isEmpty() -> MutedText(stringResource(R.string.tags_none))
                    else -> FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        t.forEach { (id, name) ->
                            TextButton(onClick = {
                                vm.adminRun("tag_remove", json("path" to item.path, "tag" to id), ok = okRemoved, reload = false) { e ->
                                    if (e == null) scope.launch { reload() } else error = e
                                }
                            }, contentPadding = PaddingValues(horizontal = 8.dp)) { Text("$name ×", color = Amber) }
                        }
                    }
                }
                Spacer(Modifier.height(8.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    FormField(stringResource(R.string.tag_add), text, { text = it }, modifier = Modifier.weight(1f), maxLength = 64)
                    TextButton(onClick = { add(text) }, enabled = text.isNotBlank()) { Text(stringResource(R.string.add)) }
                }
                val offered = names.filter { it.contains(text.trim(), ignoreCase = true) && text.isNotBlank() && t?.none { p -> p.second == it } != false }.take(8)
                if (offered.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    offered.forEach { n -> TextButton(onClick = { add(n) }, contentPadding = PaddingValues(horizontal = 8.dp)) { Text(n) } }
                }
                InlineError(error)
            }
        },
        confirmButton = { TextButton(onClick = onDone) { Text(stringResource(R.string.done)) } },
    )
}
