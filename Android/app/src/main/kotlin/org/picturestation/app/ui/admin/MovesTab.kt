// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.ui.admin

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import org.picturestation.app.AdminState
import org.picturestation.app.AdminTab
import org.picturestation.app.AppViewModel
import org.picturestation.app.R
import org.picturestation.app.data.AlbumsList
import org.picturestation.app.data.Orphan
import org.picturestation.app.data.baseName
import org.picturestation.app.data.fmtDay
import org.picturestation.app.data.json
import org.picturestation.app.ui.Amber
import org.picturestation.app.ui.Danger

/** Albums that moved on disk: ambiguous ones to resolve, settings of albums that are gone, and the history. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun MovesTab(vm: AppViewModel, st: AdminState) {
    val ctx = LocalContext.current
    var pickFor by remember { mutableStateOf<String?>(null) }
    var deleting by remember { mutableStateOf<Orphan?>(null) }
    val okMoved = stringResource(R.string.moves_moved)
    val okDeleted = stringResource(R.string.deleted)
    LaunchedEffect(st.moves == null) { vm.adminLoadTab(AdminTab.MOVES) }
    val m = st.moves
    LazyColumn(modifier = Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { MutedText(stringResource(R.string.moves_help)) }
        if (m == null) { item { Spinner() }; return@LazyColumn }
        if (m.pending.isNotEmpty()) item {
            AdminCard {
                SectionTitle(stringResource(R.string.moves_pending))
                MutedText(stringResource(R.string.moves_pending_help))
                m.pending.forEach { p ->
                    Text(p.old, fontWeight = FontWeight.Bold)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        p.candidates.forEach { c ->
                            TextButton(onClick = { vm.adminRun("moves_remap", json("old" to p.old, "new" to c), ok = ctx.getString(R.string.moves_moved_to, c)) }) {
                                Text("→ $c", color = Amber)
                            }
                        }
                    }
                }
            }
        }
        item { SectionTitle(stringResource(R.string.moves_orphans)) }
        if (m.orphans.isEmpty()) item { MutedText(stringResource(R.string.moves_none)) }
        else items(m.orphans, key = { it.path }) { o ->
            AdminCard {
                Text(o.path, fontWeight = FontWeight.Bold)
                MutedText(orphanSummary(o))
                Row {
                    TextButton(onClick = { pickFor = o.path }) { Text(stringResource(R.string.moves_where), color = Amber) }
                    TextButton(onClick = { deleting = o }) { Text(stringResource(R.string.delete), color = Danger) }
                }
            }
        }
        item { SectionTitle(stringResource(R.string.moves_history)) }
        if (m.history.isEmpty()) item { MutedText(stringResource(R.string.none_yet)) }
        else items(m.history.size) { i ->
            val h = m.history[i]
            MutedText(fmtDay(h.created) + " · " + h.old + " → " + h.new + " (" +
                stringResource(if (h.kind == "manual") R.string.moves_manual else R.string.moves_auto) + ")")
        }
    }
    pickFor?.let { old ->
        AlbumPickerDialog(vm, title = stringResource(R.string.pick_where), hint = stringResource(R.string.pick_hint, old),
            onPick = { new -> pickFor = null; vm.adminRun("moves_remap", json("old" to old, "new" to new), ok = okMoved) },
            onDismiss = { pickFor = null })
    }
    deleting?.let { o ->
        ConfirmDialog(text = stringResource(R.string.moves_delete_q, o.path), confirmLabel = stringResource(R.string.delete),
            onConfirm = { vm.adminRun("orphan_delete", json("path" to o.path), ok = okDeleted) }, onDismiss = { deleting = null })
    }
}

@Composable
private fun orphanSummary(o: Orphan): String {
    val ctx = LocalContext.current
    val parts = ArrayList<String>()
    if (o.rules > 0) parts.add(ctx.resources.getQuantityString(R.plurals.moves_rules, o.rules, o.rules))
    if (o.props) parts.add(ctx.getString(R.string.moves_props))
    if (o.shares > 0) parts.add(ctx.resources.getQuantityString(R.plurals.moves_links, o.shares, o.shares))
    if (o.smart > 0) parts.add(ctx.resources.getQuantityString(R.plurals.moves_smart, o.smart, o.smart))
    if (o.nested > 0) parts.add("+ " + ctx.resources.getQuantityString(R.plurals.moves_nested, o.nested, o.nested))
    return parts.joinToString(", ")
}

/** Walks the album tree (one level at a time) and hands back the chosen album's path. */
@Composable
fun AlbumPickerDialog(vm: AppViewModel, title: String, hint: String, onPick: (String) -> Unit, onDismiss: () -> Unit) {
    var path by remember { mutableStateOf("") }
    var list by remember { mutableStateOf<AlbumsList?>(null) }
    LaunchedEffect(path) { list = null; list = vm.adminFetch { albums(path) } }
    val whole = stringResource(R.string.whole_library)
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column(modifier = Modifier.verticalScroll(rememberScrollState())) {
                MutedText(hint)
                Crumbs(path) { path = it }
                val l = list
                when {
                    l == null -> Spinner()
                    l.albums.isEmpty() -> MutedText(stringResource(R.string.acc_no_sub, l.files))
                    else -> l.albums.forEach { name ->
                        TextButton(onClick = { path = if (path.isEmpty()) name else "$path/$name" }, contentPadding = PaddingValues(horizontal = 4.dp)) {
                            Text("$name ›", color = Amber)
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = { onPick(path) }, enabled = path.isNotEmpty()) {
                Text(stringResource(R.string.pick_select, if (path.isEmpty()) whole else baseName(path)))
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text(stringResource(R.string.cancel)) } },
    )
}
