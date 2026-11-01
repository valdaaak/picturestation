// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.ui.admin

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import org.picturestation.app.AdminState
import org.picturestation.app.AppViewModel
import org.picturestation.app.R
import org.picturestation.app.Screen
import org.picturestation.app.data.AdminGroup
import org.picturestation.app.data.AdminInfo
import org.picturestation.app.data.AdminUser
import org.picturestation.app.data.Grant
import org.picturestation.app.data.json
import org.picturestation.app.ui.Amber
import org.picturestation.app.ui.Danger

/** The users, groups and the guest of the gallery, with their albums (like the web's Settings tabs). */

private fun lazyColumn() = Modifier.fillMaxSize().imePadding()

/** Removes one rule of a principal and says what happened. */
private fun revokeGrant(vm: AppViewModel, type: String, name: String, g: Grant, okRemoved: String, okCancelled: String) {
    vm.adminRun("revoke", json("type" to type, "name" to name, "path" to g.path), ok = if (g.deny) okCancelled else okRemoved)
}

// ---------- users ----------
@Composable
fun UsersTab(vm: AppViewModel, st: AdminState, info: AdminInfo) {
    var editing by remember { mutableStateOf<String?>(null) }
    LazyColumn(modifier = lazyColumn(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { NewUserForm(vm, st) }
        items(info.users, key = { it.username }) { u -> UserCard(vm, u) { editing = u.username } }
    }
    editing?.let { name ->
        info.users.firstOrNull { it.username == name }?.let { u -> UserDialog(vm, st, u, info.groups) { editing = null } }
    }
}

@Composable
private fun NewUserForm(vm: AppViewModel, st: AdminState) {
    var name by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var note by remember { mutableStateOf("") }
    var admin by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val okCreated = stringResource(R.string.user_created)
    val short = stringResource(R.string.user_pw_short)
    AdminCard {
        SectionTitle(stringResource(R.string.user_new))
        Spacer(Modifier.height(8.dp))
        FormField(stringResource(R.string.name), name, { name = it })
        Spacer(Modifier.height(8.dp))
        FormField(stringResource(R.string.password_min8), password, { password = it }, password = true)
        Spacer(Modifier.height(8.dp))
        FormField(stringResource(R.string.note), note, { note = it })
        CheckRow(stringResource(R.string.user_admin_long), admin, { admin = it })
        Button(
            onClick = {
                if (password.length < 8) { error = short; return@Button }
                error = null
                vm.adminRun("user_create", json("username" to name.trim(), "password" to password, "note" to note.trim(), "admin" to admin), ok = okCreated) { e ->
                    error = e; if (e == null) { name = ""; password = ""; note = ""; admin = false }
                }
            },
            enabled = name.isNotBlank() && password.isNotEmpty() && !st.busy, modifier = Modifier.fillMaxWidth(),
        ) { Text(stringResource(R.string.add)) }
        InlineError(error)
    }
}

@Composable
private fun UserCard(vm: AppViewModel, u: AdminUser, onEdit: () -> Unit) {
    val okRemoved = stringResource(R.string.grant_removed)
    val okCancelled = stringResource(R.string.grant_excl_cancelled)
    AdminCard {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(u.username, fontWeight = FontWeight.Bold)
            if (u.admin) Tag(stringResource(R.string.user_admin), TagKind.ACCENT)
            if (u.disabled) Tag(stringResource(R.string.user_disabled), TagKind.BAD)
            Spacer(Modifier.weight(1f))
            TextButton(onClick = onEdit) { Text(stringResource(R.string.edit), color = Amber) }
        }
        if (u.note.isNotEmpty()) MutedText(u.note)
        if (u.admin) MutedText(stringResource(R.string.user_sees_all))
        else {
            MutedText(stringResource(R.string.user_groups, u.groups.joinToString(", ").ifEmpty { stringResource(R.string.nobody) }))
            Spacer(Modifier.height(6.dp))
            GrantChips(u.grants, stringResource(R.string.grants_none),
                onRevoke = { revokeGrant(vm, "user", u.username, it, okRemoved, okCancelled) },
                onEdit = { vm.push(Screen.Access("user", u.username, "")) })
        }
    }
}

@Composable
private fun UserDialog(vm: AppViewModel, st: AdminState, u: AdminUser, groups: List<AdminGroup>, onClose: () -> Unit) {
    var note by remember { mutableStateOf(u.note) }
    var password by remember { mutableStateOf("") }
    var admin by remember { mutableStateOf(u.admin) }
    var disabled by remember { mutableStateOf(u.disabled) }
    var members by remember { mutableStateOf(u.groups.toSet()) }
    var error by remember { mutableStateOf<String?>(null) }
    var confirmDelete by remember { mutableStateOf(false) }
    val okSaved = stringResource(R.string.saved)
    val okDeleted = stringResource(R.string.user_deleted)
    val short = stringResource(R.string.user_pw_short)
    AlertDialog(
        onDismissRequest = onClose,
        title = { Text(u.username) },
        text = {
            Column(modifier = Modifier.verticalScroll(rememberScrollState())) {
                FormField(stringResource(R.string.note), note, { note = it })
                Spacer(Modifier.height(8.dp))
                FormField(stringResource(R.string.user_new_password), password, { password = it }, password = true,
                    placeholder = stringResource(R.string.user_pw_keep))
                CheckRow(stringResource(R.string.user_admin_long), admin, { admin = it })
                CheckRow(stringResource(R.string.user_disabled), disabled, { disabled = it })
                if (groups.isNotEmpty()) {
                    Spacer(Modifier.height(6.dp))
                    SectionTitle(stringResource(R.string.groups_label))
                    groups.forEach { g -> CheckRow(g.name, g.name in members, { on -> members = if (on) members + g.name else members - g.name }) }
                }
                InlineError(error)
                TextButton(onClick = { confirmDelete = true }) { Text(stringResource(R.string.delete), color = Danger) }
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    if (password.isNotEmpty() && password.length < 8) { error = short; return@TextButton }
                    error = null
                    vm.adminRun("user_update", json("username" to u.username, "note" to note.trim(), "admin" to admin, "disabled" to disabled,
                        "groups" to members.toList(), "password" to password.ifEmpty { null }), ok = okSaved) { e -> if (e == null) onClose() else error = e }
                },
                enabled = !st.busy,
            ) { Text(stringResource(R.string.save)) }
        },
        dismissButton = { TextButton(onClick = onClose) { Text(stringResource(R.string.cancel)) } },
    )
    if (confirmDelete) ConfirmDialog(
        text = stringResource(R.string.user_delete_q, u.username), confirmLabel = stringResource(R.string.delete),
        onConfirm = { vm.adminRun("user_delete", json("username" to u.username), ok = okDeleted) { e -> if (e == null) onClose() else error = e } },
        onDismiss = { confirmDelete = false },
    )
}

// ---------- groups ----------
@Composable
fun GroupsTab(vm: AppViewModel, st: AdminState, info: AdminInfo) {
    var editing by remember { mutableStateOf<String?>(null) }
    LazyColumn(modifier = lazyColumn(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { NewGroupForm(vm, st) }
        if (info.groups.isEmpty()) item { MutedText(stringResource(R.string.group_hint)) }
        items(info.groups, key = { it.name }) { g -> GroupCard(vm, g) { editing = g.name } }
    }
    editing?.let { name ->
        info.groups.firstOrNull { it.name == name }?.let { g -> GroupDialog(vm, st, g, info.users) { editing = null } }
    }
}

@Composable
private fun NewGroupForm(vm: AppViewModel, st: AdminState) {
    var name by remember { mutableStateOf("") }
    var note by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    val okCreated = stringResource(R.string.group_created)
    AdminCard {
        SectionTitle(stringResource(R.string.group_new))
        Spacer(Modifier.height(8.dp))
        FormField(stringResource(R.string.title_label), name, { name = it })
        Spacer(Modifier.height(8.dp))
        FormField(stringResource(R.string.note), note, { note = it })
        Spacer(Modifier.height(8.dp))
        Button(
            onClick = {
                error = null
                vm.adminRun("group_create", json("name" to name.trim(), "note" to note.trim()), ok = okCreated) { e ->
                    error = e; if (e == null) { name = ""; note = "" }
                }
            },
            enabled = name.isNotBlank() && !st.busy, modifier = Modifier.fillMaxWidth(),
        ) { Text(stringResource(R.string.add)) }
        InlineError(error)
    }
}

@Composable
private fun GroupCard(vm: AppViewModel, g: AdminGroup, onEdit: () -> Unit) {
    val okRemoved = stringResource(R.string.grant_removed)
    val okCancelled = stringResource(R.string.grant_excl_cancelled)
    AdminCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(g.name, fontWeight = FontWeight.Bold)
            Spacer(Modifier.weight(1f))
            TextButton(onClick = onEdit) { Text(stringResource(R.string.edit), color = Amber) }
        }
        if (g.note.isNotEmpty()) MutedText(g.note)
        MutedText(stringResource(R.string.group_members, g.members.joinToString(", ").ifEmpty { stringResource(R.string.nobody) }))
        Spacer(Modifier.height(6.dp))
        GrantChips(g.grants, stringResource(R.string.grants_none),
            onRevoke = { revokeGrant(vm, "group", g.name, it, okRemoved, okCancelled) },
            onEdit = { vm.push(Screen.Access("group", g.name, "")) })
    }
}

@Composable
private fun GroupDialog(vm: AppViewModel, st: AdminState, g: AdminGroup, users: List<AdminUser>, onClose: () -> Unit) {
    var note by remember { mutableStateOf(g.note) }
    var members by remember { mutableStateOf(g.members.toSet()) }
    var error by remember { mutableStateOf<String?>(null) }
    var confirmDelete by remember { mutableStateOf(false) }
    val okSaved = stringResource(R.string.saved)
    val okDeleted = stringResource(R.string.group_deleted)
    AlertDialog(
        onDismissRequest = onClose,
        title = { Text(stringResource(R.string.group_fmt, g.name)) },
        text = {
            Column(modifier = Modifier.verticalScroll(rememberScrollState())) {
                FormField(stringResource(R.string.note), note, { note = it })
                Spacer(Modifier.height(6.dp))
                SectionTitle(stringResource(R.string.members))
                users.forEach { u -> CheckRow(u.username, u.username in members, { on -> members = if (on) members + u.username else members - u.username }) }
                InlineError(error)
                TextButton(onClick = { confirmDelete = true }) { Text(stringResource(R.string.delete), color = Danger) }
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    error = null
                    vm.adminRun("group_update", json("name" to g.name, "note" to note.trim(), "members" to members.toList()), ok = okSaved) { e ->
                        if (e == null) onClose() else error = e
                    }
                },
                enabled = !st.busy,
            ) { Text(stringResource(R.string.save)) }
        },
        dismissButton = { TextButton(onClick = onClose) { Text(stringResource(R.string.cancel)) } },
    )
    if (confirmDelete) ConfirmDialog(
        text = stringResource(R.string.group_delete_q, g.name), confirmLabel = stringResource(R.string.delete),
        onConfirm = { vm.adminRun("group_delete", json("name" to g.name), ok = okDeleted) { e -> if (e == null) onClose() else error = e } },
        onDismiss = { confirmDelete = false },
    )
}

// ---------- without signing in ----------
@Composable
fun GuestTab(vm: AppViewModel, st: AdminState, info: AdminInfo) {
    val okRemoved = stringResource(R.string.grant_removed)
    val okCancelled = stringResource(R.string.grant_excl_cancelled)
    val okOn = stringResource(R.string.guest_root_on)
    val okOff = stringResource(R.string.guest_root_off)
    LazyColumn(modifier = lazyColumn(), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item { MutedText(stringResource(R.string.guest_help)) }
        item {
            AdminCard {
                CheckRow(stringResource(R.string.guest_root_public), info.settings.flags["root_files_public"] == true,
                    { v -> vm.adminRun("settings", json("root_files_public" to v), ok = if (v) okOn else okOff) },
                    hint = stringResource(R.string.guest_root_hint), enabled = !st.busy)
            }
        }
        item {
            AdminCard {
                GrantChips(info.guestGrants, stringResource(R.string.grants_guest_none),
                    onRevoke = { revokeGrant(vm, "guest", "", it, okRemoved, okCancelled) },
                    onEdit = { vm.push(Screen.Access("guest", "", "")) })
            }
        }
    }
    Spacer(Modifier.width(0.dp))
}
