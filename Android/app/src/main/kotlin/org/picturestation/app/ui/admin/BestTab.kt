// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.ui.admin

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import coil.compose.AsyncImage
import org.json.JSONArray
import org.picturestation.app.AdminState
import org.picturestation.app.AdminTab
import org.picturestation.app.AppViewModel
import org.picturestation.app.R
import org.picturestation.app.data.BestProposal
import org.picturestation.app.data.fmtDay
import org.picturestation.app.data.json
import org.picturestation.app.ui.Amber
import org.picturestation.app.ui.Danger

/** The web's Settings, Best Foto: the photos users suggested for the tag, with who suggested them; the
 *  administrator approves (the tag is added) or rejects (the suggestion is dropped), one by one or all at once. */
@Composable
fun BestTab(vm: AppViewModel, st: AdminState) {
    val ctx = LocalContext.current
    var big by remember { mutableStateOf<BestProposal?>(null) }
    var all by remember { mutableStateOf(false) }
    LaunchedEffect(st.best == null) { vm.adminLoadTab(AdminTab.BEST) }
    val list = st.best

    fun approve(paths: List<String>) {
        vm.adminRun("best_approve", json("paths" to JSONArray(paths)),
            ok = ctx.resources.getQuantityString(R.plurals.best_approved, paths.size, paths.size)) { e -> if (e == null) vm.markBrowseStale() }
    }

    LazyColumn(modifier = Modifier.fillMaxSize(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { MutedText(stringResource(R.string.best_adm_help)) }
        when {
            list == null -> item { Spinner() }
            list.isEmpty() -> item { MutedText(stringResource(R.string.best_adm_none)) }
            else -> {
                if (list.size > 1) item {
                    TextButton(onClick = { all = true }, enabled = !st.busy) {
                        Text(pluralStringResource(R.plurals.best_approve_all, list.size, list.size), color = Amber)
                    }
                }
                items(list, key = { it.path }) { p ->
                    AdminCard {
                        Box(modifier = Modifier.fillMaxWidth().height(220.dp).clip(RoundedCornerShape(8.dp)).background(Color.Black)
                            .clickable { big = p }) {
                            AsyncImage(model = vm.api.thumbUrl(p.item, "small"), contentDescription = p.item.title,
                                contentScale = ContentScale.Fit, modifier = Modifier.fillMaxSize())
                        }
                        Text(p.path.substringAfterLast('/'), fontWeight = FontWeight.Bold)
                        MutedText(p.path.substringBeforeLast('/', ""))
                        MutedText(stringResource(R.string.best_adm_by, p.users.joinToString(", "), fmtDay(p.created)))
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            TextButton(onClick = { approve(listOf(p.path)) }, enabled = !st.busy) {
                                Text(stringResource(R.string.best_approve), color = Amber)
                            }
                            TextButton(onClick = {
                                vm.adminRun("best_reject", json("paths" to JSONArray(listOf(p.path))), ok = ctx.getString(R.string.best_rejected))
                            }, enabled = !st.busy) { Text(stringResource(R.string.best_reject), color = Danger) }
                        }
                    }
                }
            }
        }
    }
    if (all && list != null) {
        ConfirmDialog(text = pluralStringResource(R.plurals.best_approve_all_q, list.size, list.size),
            confirmLabel = stringResource(R.string.best_approve),
            onConfirm = { approve(list.map { it.path }) }, onDismiss = { all = false })
    }
    big?.let { p ->
        Dialog(onDismissRequest = { big = null }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
            Box(modifier = Modifier.fillMaxSize().background(Color.Black).clickable { big = null }) {
                AsyncImage(model = vm.api.thumbUrl(p.item, "large"), contentDescription = p.item.title,
                    contentScale = ContentScale.Fit, modifier = Modifier.fillMaxSize())
            }
        }
    }
}
