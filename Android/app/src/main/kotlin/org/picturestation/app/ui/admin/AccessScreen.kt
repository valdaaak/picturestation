// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.ui.admin

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch
import org.picturestation.app.AppViewModel
import org.picturestation.app.R
import org.picturestation.app.Screen
import org.picturestation.app.data.AccessState
import org.picturestation.app.data.AccessView
import org.picturestation.app.data.AdminApi
import org.picturestation.app.data.AlbumAccess
import org.picturestation.app.data.Via
import org.picturestation.app.data.baseName
import org.picturestation.app.ui.Amber
import org.picturestation.app.ui.Danger
import org.picturestation.app.ui.Paper

/** "valde", "Group family" or "Without signing in". */
@Composable
fun principalLabel(type: String, name: String): String = when (type) {
    "guest" -> stringResource(R.string.tab_guest)
    "group" -> stringResource(R.string.group_fmt, name)
    else -> name
}

/** The access editor of one user, group or guest, one album level per screen: what they see below `s.path`
 *  and the rules to change it. Back and the breadcrumbs lead up. */
@Composable
fun AccessScreen(vm: AppViewModel, s: Screen.Access) {
    var view by remember { mutableStateOf<AccessView?>(null) }
    var loading by remember { mutableStateOf(true) }
    var reload by remember { mutableIntStateOf(0) }
    LaunchedEffect(reload) { loading = true; view = vm.adminFetch { accessView(s.type, s.name, s.path) }; loading = false }
    val whole = stringResource(R.string.whole_library)
    AdminScaffold(title = stringResource(R.string.access_title, principalLabel(s.type, s.name)), onBack = { vm.pop() }) { pad ->
        LazyColumn(modifier = Modifier.fillMaxSize().padding(pad), contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item { Crumbs(s.path) { vm.popAccessTo(it) } }
            item { MutedText(stringResource(R.string.access_help)) }
            val v = view
            if (v == null) item { if (loading) Spinner() else MutedText(stringResource(R.string.load_failed)) }
            else {
                item {
                    AdminCard {
                        AccessStateRow(if (s.path.isEmpty()) whole else baseName(s.path), v.self, onOpen = null)
                        AccessButtons(vm, v.self, s.type, s.name, s.path) { reload++ }
                    }
                }
                if (v.albums.isEmpty()) item { MutedText(stringResource(R.string.acc_no_sub, v.files)) }
                else items(v.albums, key = { it.path }) { row ->
                    AdminCard {
                        AccessStateRow(row.name, row.state, onOpen = { vm.push(Screen.Access(s.type, s.name, row.path)) })
                        AccessButtons(vm, row.state, s.type, s.name, row.path) { reload++ }
                    }
                }
            }
        }
    }
}

/** Who sees one album: every user, group and the guest with their rule, and the buttons to change it. */
@Composable
fun AlbumAccessScreen(vm: AppViewModel, path: String) {
    var view by remember { mutableStateOf<AlbumAccess?>(null) }
    var loading by remember { mutableStateOf(true) }
    var reload by remember { mutableIntStateOf(0) }
    LaunchedEffect(reload) { loading = true; view = vm.adminFetch { albumAccess(path) }; loading = false }
    val disabledWord = stringResource(R.string.user_disabled)
    AdminScaffold(title = stringResource(R.string.access_album_title, baseName(path)), onBack = { vm.pop() }) { pad ->
        LazyColumn(modifier = Modifier.fillMaxSize().padding(pad), contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item { MutedText(stringResource(R.string.access_album_help)) }
            val v = view
            if (v == null) item { if (loading) Spinner() else MutedText(stringResource(R.string.load_failed)) }
            else items(v.principals, key = { it.type + ":" + it.name }) { p ->
                AdminCard {
                    val label = principalLabel(p.type, p.name) + (if (p.disabled) " ($disabledWord)" else "")
                    AccessStateRow(label, p.state, onOpen = null)
                    AccessButtons(vm, p.state, p.type, p.name, path) { reload++ }
                }
            }
        }
    }
}

/** One row of the editor: the name, the own rule, what is effectively seen, and where that comes from. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun AccessStateRow(name: String, state: AccessState, onOpen: (() -> Unit)?) {
    FlowRow(verticalArrangement = Arrangement.Center, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        if (onOpen != null) TextButton(onClick = onOpen, contentPadding = PaddingValues(0.dp)) { Text("$name ›", color = Amber, fontWeight = FontWeight.Bold) }
        else Text(name, color = Paper, fontWeight = FontWeight.Bold, modifier = Modifier.padding(vertical = 8.dp))
        Row(modifier = Modifier.padding(vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
            when (state.rule) {
                "allow" -> Tag(stringResource(R.string.acc_allowed_tag), TagKind.ACCENT)
                "deny" -> Tag(stringResource(R.string.acc_excluded_tag), TagKind.BAD)
            }
            EffectiveBadge(state.effective)
        }
    }
    viaText(state.via)?.let { MutedText(it) }
}

@Composable
private fun EffectiveBadge(effective: String) {
    when (effective) {
        "all" -> Tag(stringResource(R.string.acc_all), TagKind.ACCENT)
        "yes" -> Tag(stringResource(R.string.acc_yes), TagKind.ACCENT)
        "path" -> Tag(stringResource(R.string.acc_path), TagKind.PLAIN)
        else -> Tag(stringResource(R.string.acc_no), TagKind.BAD)
    }
}

@Composable
private fun viaText(via: Via?): String? {
    via ?: return null
    if (via.admin) return stringResource(R.string.acc_via_admin)
    val ctx = LocalContext.current
    val where = via.path.ifEmpty { stringResource(R.string.acc_whole) }
    val base = stringResource(if (via.deny) R.string.acc_via_excluded else R.string.acc_via_allowed, where)
    return if (via.groups.isEmpty()) base
    else base + " (" + via.groups.joinToString(", ") { ctx.getString(R.string.group_fmt, it) } + ")"
}

/** Allow / Exclude / Remove rule / Allow all inside, shown as the web shows them for this state. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun AccessButtons(vm: AppViewModel, state: AccessState, type: String, name: String, path: String, onChanged: () -> Unit) {
    if (state.effective == "all") return
    val scope = rememberCoroutineScope()
    val okAllowed = stringResource(R.string.acc_allowed)
    val okExcluded = stringResource(R.string.acc_excluded)
    val okRemoved = stringResource(R.string.acc_rule_removed)
    val whole = stringResource(R.string.whole_library)
    var confirmAll by remember { mutableStateOf(false) }
    fun run(ok: String, block: suspend AdminApi.() -> Unit) {
        scope.launch { if (vm.adminFetch { block(); true } == true) { vm.message = ok; onChanged() } }
    }
    val showAllow = state.rule == "deny" || (state.rule != "allow" && state.effective != "yes")
    val showExclude = state.rule != "deny" && path.isNotEmpty()
    val showRemove = state.rule != null
    val n = state.below.size
    FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        if (showAllow) TextButton(onClick = { run(okAllowed) { grant(type, name, path) } }) { Text(stringResource(R.string.acc_allow), color = Amber) }
        if (showExclude) TextButton(onClick = { run(okExcluded) { grant(type, name, path, deny = true) } }) { Text(stringResource(R.string.acc_exclude), color = Danger) }
        if (showRemove) TextButton(onClick = { run(okRemoved) { revoke(type, name, path) } }) { Text(stringResource(R.string.acc_remove_rule)) }
        if (n > 0) TextButton(onClick = { confirmAll = true }) { Text(pluralStringResource(R.plurals.acc_allow_all, n, n), color = Amber) }
    }
    if (confirmAll) ConfirmDialog(
        text = stringResource(R.string.acc_allow_all_q, path.ifEmpty { whole }) + "\n\n" + state.below.take(15).joinToString("\n"),
        confirmLabel = stringResource(R.string.acc_allow),
        onConfirm = { run(okAllowed) { grant(type, name, path, clearBelow = true) } }, onDismiss = { confirmAll = false },
    )
    Spacer(Modifier.width(0.dp))
}
