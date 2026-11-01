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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import org.picturestation.app.AdminState
import org.picturestation.app.AdminTab
import org.picturestation.app.AppViewModel
import org.picturestation.app.R
import org.picturestation.app.data.AdminInfo
import org.picturestation.app.data.Device
import org.picturestation.app.data.fmtDay
import org.picturestation.app.data.json
import org.picturestation.app.ui.Danger

/** Paired TVs (and phones): allow the code a TV shows, under a user; remove a device. */
@Composable
fun TvTab(vm: AppViewModel, st: AdminState, info: AdminInfo) {
    var code by remember { mutableStateOf("") }
    var user by remember { mutableStateOf(vm.user) }
    var error by remember { mutableStateOf<String?>(null) }
    var removing by remember { mutableStateOf<Device?>(null) }
    val okAllowed = stringResource(R.string.tv_allowed)
    val okRemoved = stringResource(R.string.tv_removed)
    LaunchedEffect(Unit) { vm.adminLoadTab(AdminTab.TV) }
    val users = info.users.filter { !it.disabled }.map { it.username to it.username }

    LazyColumn(
        modifier = Modifier.fillMaxSize().imePadding(), contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item { MutedText(stringResource(R.string.tv_help)) }
        item {
            AdminCard {
                FormField(stringResource(R.string.tv_code), code, { code = it.uppercase() },
                    capitalization = KeyboardCapitalization.Characters, maxLength = 7, placeholder = "ABC123")
                Spacer(Modifier.height(8.dp))
                OptionPicker(stringResource(R.string.tv_user), users, user) { user = it }
                Spacer(Modifier.height(8.dp))
                Button(
                    onClick = {
                        error = null
                        vm.adminRun("device_pair", json("code" to code.trim(), "user" to user), ok = okAllowed) { e ->
                            error = e; if (e == null) code = ""
                        }
                    },
                    enabled = code.trim().length >= 6 && user.isNotEmpty() && !st.busy, modifier = Modifier.fillMaxWidth(),
                ) { Text(stringResource(R.string.tv_allow)) }
                InlineError(error)
            }
        }
        val devs = st.devices
        when {
            devs == null -> item { Spinner() }
            devs.isEmpty() -> item { MutedText(stringResource(R.string.tv_none)) }
            else -> items(devs, key = { it.id }) { d -> DeviceCard(d) { removing = d } }
        }
    }
    removing?.let { d ->
        ConfirmDialog(text = stringResource(R.string.tv_remove_q), confirmLabel = stringResource(R.string.remove),
            onConfirm = { vm.adminRun("device_delete", json("id" to d.id), ok = okRemoved) }, onDismiss = { removing = null })
    }
}

@Composable
private fun DeviceCard(d: Device, onRemove: () -> Unit) {
    AdminCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f)) {
                Text(d.name, fontWeight = FontWeight.Bold)
                Row { Tag(d.username, TagKind.ACCENT) }
                val seen = d.lastSeen?.let { stringResource(R.string.tv_last_seen, fmtDay(it)) } ?: stringResource(R.string.tv_not_used)
                MutedText(stringResource(R.string.tv_allowed_on, fmtDay(d.created)) + " · " + seen)
            }
            TextButton(onClick = onRemove) { Text(stringResource(R.string.remove), color = Danger) }
        }
    }
}
