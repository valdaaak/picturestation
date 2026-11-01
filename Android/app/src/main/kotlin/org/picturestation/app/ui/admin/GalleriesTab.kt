// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.ui.admin

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import org.picturestation.app.AdminState
import org.picturestation.app.AdminTab
import org.picturestation.app.AppViewModel
import org.picturestation.app.R
import org.picturestation.app.data.PrivateGallery
import org.picturestation.app.data.json
import org.picturestation.app.ui.Amber
import org.picturestation.app.ui.Danger

/** The private galleries of this server (main gallery only): create, administrators, on/off, delete. */
@Composable
fun GalleriesTab(vm: AppViewModel, st: AdminState) {
    var editing by remember { mutableStateOf<String?>(null) }
    var adminOf by remember { mutableStateOf<String?>(null) }
    var removingAdmin by remember { mutableStateOf<Pair<String, String>?>(null) }
    val okRemoved = stringResource(R.string.saved)
    LaunchedEffect(st.galleries == null) { vm.adminLoadTab(AdminTab.GALLERIES) }
    val list = st.galleries
    LazyColumn(modifier = Modifier.fillMaxSize().imePadding(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { MutedText(stringResource(R.string.gal_help)) }
        when {
            list == null -> item { Spinner() }
            else -> {
                item { NewGalleryForm(vm, st, list.roots) }
                if (list.galleries.isEmpty()) item { MutedText(stringResource(R.string.gal_none)) }
                items(list.galleries, key = { it.name }) { g ->
                    GalleryCard(vm, g, onEdit = { editing = g.name }, onAddAdmin = { adminOf = g.name },
                        onRemoveAdmin = { removingAdmin = g.name to it })
                }
            }
        }
    }
    editing?.let { name -> list?.galleries?.firstOrNull { it.name == name }?.let { g -> GalleryDialog(vm, st, g) { editing = null } } }
    adminOf?.let { name -> GalleryAdminDialog(vm, st, name) { adminOf = null } }
    removingAdmin?.let { (name, user) ->
        ConfirmDialog(text = stringResource(R.string.gal_admin_remove_q, user), confirmLabel = stringResource(R.string.remove),
            onConfirm = { vm.adminRun("gallery_admin_remove", json("name" to name, "user" to user), ok = okRemoved) },
            onDismiss = { removingAdmin = null })
    }
}

@Composable
private fun NewGalleryForm(vm: AppViewModel, st: AdminState, roots: List<String>) {
    var name by remember { mutableStateOf("") }
    var title by remember { mutableStateOf("") }
    var root by remember { mutableStateOf("") }
    var hosts by remember { mutableStateOf("") }
    var admin by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    val okCreated = stringResource(R.string.gal_created)
    val short = stringResource(R.string.user_pw_short)
    AdminCard {
        SectionTitle(stringResource(R.string.gal_new))
        Spacer(Modifier.height(8.dp))
        FormField(stringResource(R.string.gal_name), name, { name = it.lowercase().filter { c -> c.isLetterOrDigit() || c == '-' } })
        Spacer(Modifier.height(8.dp))
        FormField(stringResource(R.string.title_label), title, { title = it })
        Spacer(Modifier.height(8.dp))
        FormField(stringResource(R.string.gal_root), root, { root = it }, placeholder = (roots.firstOrNull() ?: "") + "/…", keyboardType = KeyboardType.Uri)
        MutedText(stringResource(R.string.gal_roots_hint, roots.joinToString(", ")))
        Spacer(Modifier.height(8.dp))
        FormField(stringResource(R.string.gal_hosts), hosts, { hosts = it }, placeholder = "photos.example.com", keyboardType = KeyboardType.Uri)
        Spacer(Modifier.height(8.dp))
        FormField(stringResource(R.string.gal_admin), admin, { admin = it })
        Spacer(Modifier.height(8.dp))
        FormField(stringResource(R.string.password_min8), password, { password = it }, password = true)
        Spacer(Modifier.height(8.dp))
        Button(
            onClick = {
                if (password.length < 8) { error = short; return@Button }
                error = null
                vm.adminRun("gallery_create", json("name" to name, "title" to title.trim(), "root" to root.trim(), "hostnames" to hosts.trim(),
                    "admin" to admin.trim(), "password" to password), ok = okCreated) { e ->
                    error = e; if (e == null) { name = ""; title = ""; root = ""; hosts = ""; admin = ""; password = "" }
                }
            },
            enabled = name.isNotBlank() && root.isNotBlank() && admin.isNotBlank() && password.isNotEmpty() && !st.busy,
            modifier = Modifier.fillMaxWidth(),
        ) { Text(stringResource(R.string.create)) }
        InlineError(error)
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun GalleryCard(vm: AppViewModel, g: PrivateGallery, onEdit: () -> Unit, onAddAdmin: () -> Unit, onRemoveAdmin: (String) -> Unit) {
    val ctx = LocalContext.current
    val url = vm.api.server + g.path.trimEnd('/')
    AdminCard {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(g.title.ifEmpty { g.name }, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
            if (!g.enabled) Tag(stringResource(R.string.gal_off), TagKind.BAD)
            if (!g.rootOk) Tag(stringResource(R.string.gal_root_bad), TagKind.BAD)
            TextButton(onClick = onEdit) { Text(stringResource(R.string.edit), color = Amber) }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            MutedText((url + g.hostnames.joinToString("") { "\n" + it }), Modifier.weight(1f))
            TextButton(onClick = { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) }) { Text(stringResource(R.string.open), color = Amber) }
        }
        MutedText(g.root + (g.files?.let { " · " + pluralStringResource(R.plurals.gal_files, it, it) } ?: ""))
        Spacer(Modifier.height(6.dp))
        MutedText(stringResource(R.string.gal_admins))
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            g.admins.forEach { a -> TextButton(onClick = { onRemoveAdmin(a) }) { Text("$a ×") } }
        }
        TextButton(onClick = onAddAdmin) { Text(stringResource(R.string.gal_admin_add), color = Amber) }
        if (g.hostnames.isNotEmpty()) MutedText(stringResource(R.string.gal_proxy_hint, g.hostnames.first()))
    }
}

@Composable
private fun GalleryDialog(vm: AppViewModel, st: AdminState, g: PrivateGallery, onClose: () -> Unit) {
    var title by remember { mutableStateOf(g.title) }
    var root by remember { mutableStateOf(g.root) }
    var hosts by remember { mutableStateOf(g.hostnames.joinToString(" ")) }
    var enabled by remember { mutableStateOf(g.enabled) }
    var error by remember { mutableStateOf<String?>(null) }
    var confirmDelete by remember { mutableStateOf(false) }
    val okSaved = stringResource(R.string.saved)
    val okDeleted = stringResource(R.string.deleted)
    AlertDialog(
        onDismissRequest = onClose,
        title = { Text(stringResource(R.string.gal_fmt, g.name)) },
        text = {
            Column(modifier = Modifier.verticalScroll(rememberScrollState())) {
                FormField(stringResource(R.string.title_label), title, { title = it })
                Spacer(Modifier.height(8.dp))
                FormField(stringResource(R.string.gal_root), root, { root = it }, keyboardType = KeyboardType.Uri)
                Spacer(Modifier.height(8.dp))
                FormField(stringResource(R.string.gal_hosts), hosts, { hosts = it }, keyboardType = KeyboardType.Uri)
                CheckRow(stringResource(R.string.gal_on), enabled, { enabled = it })
                InlineError(error)
                TextButton(onClick = { confirmDelete = true }) { Text(stringResource(R.string.delete), color = Danger) }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                error = null
                vm.adminRun("gallery_update", json("name" to g.name, "title" to title.trim(), "root" to root.trim(), "hostnames" to hosts.trim(), "enabled" to enabled), ok = okSaved) { e ->
                    if (e == null) onClose() else error = e
                }
            }, enabled = !st.busy) { Text(stringResource(R.string.save)) }
        },
        dismissButton = { TextButton(onClick = onClose) { Text(stringResource(R.string.cancel)) } },
    )
    if (confirmDelete) ConfirmDialog(
        text = stringResource(R.string.gal_delete_q, g.name), confirmLabel = stringResource(R.string.delete),
        onConfirm = { vm.adminRun("gallery_delete", json("name" to g.name), ok = okDeleted) { e -> if (e == null) onClose() else error = e } },
        onDismiss = { confirmDelete = false },
    )
}

@Composable
private fun GalleryAdminDialog(vm: AppViewModel, st: AdminState, name: String, onClose: () -> Unit) {
    var user by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    val okSaved = stringResource(R.string.saved)
    val short = stringResource(R.string.user_pw_short)
    AlertDialog(
        onDismissRequest = onClose,
        title = { Text(stringResource(R.string.gal_admin_title, name)) },
        text = {
            Column {
                MutedText(stringResource(R.string.gal_admin_hint))
                Spacer(Modifier.height(8.dp))
                FormField(stringResource(R.string.gal_admin), user, { user = it })
                Spacer(Modifier.height(8.dp))
                FormField(stringResource(R.string.password_min8), password, { password = it }, password = true)
                InlineError(error)
            }
        },
        confirmButton = {
            TextButton(onClick = {
                if (password.length < 8) { error = short; return@TextButton }
                error = null
                vm.adminRun("gallery_admin_set", json("name" to name, "user" to user.trim(), "password" to password), ok = okSaved) { e ->
                    if (e == null) onClose() else error = e
                }
            }, enabled = user.isNotBlank() && password.isNotEmpty() && !st.busy) { Text(stringResource(R.string.save)) }
        },
        dismissButton = { TextButton(onClick = onClose) { Text(stringResource(R.string.cancel)) } },
    )
}
