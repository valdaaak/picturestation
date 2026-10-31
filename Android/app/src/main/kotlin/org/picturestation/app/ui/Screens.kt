// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.picturestation.app.AppViewModel
import org.picturestation.app.BuildConfig
import org.picturestation.app.R

@Composable
private fun Centered(content: @Composable () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) { content() }
}

@Composable
private fun Logo() {
    Text("Picturestation", fontSize = 34.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(bottom = 28.dp))
}

@Composable
fun SetupScreen(vm: AppViewModel) {
    var typed by remember { mutableStateOf(vm.store.server) }
    val noAnswer = stringResource(R.string.err_no_answer)
    val notServer = stringResource(R.string.err_not_server)
    Centered {
        Logo()
        Column(modifier = Modifier.widthIn(max = 520.dp).fillMaxWidth()) {
            Text(stringResource(R.string.server_address), style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(
                value = typed, onValueChange = { typed = it }, singleLine = true,
                placeholder = { Text(stringResource(R.string.server_hint)) },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Go,
                    capitalization = KeyboardCapitalization.None, autoCorrectEnabled = false),
                keyboardActions = KeyboardActions(onGo = { vm.connect(typed, noAnswer, notServer) }),
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(16.dp))
            Button(onClick = { vm.connect(typed, noAnswer, notServer) }, enabled = !vm.setupBusy,
                modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(if (vm.setupBusy) R.string.connecting else R.string.connect))
            }
            vm.setupError?.let {
                Spacer(Modifier.height(12.dp))
                Text(it, color = MaterialTheme.colorScheme.error)
            }
            vm.setupHttpOffer?.let { http ->
                Spacer(Modifier.height(12.dp))
                Text(stringResource(R.string.http_warning), color = Muted)
                Spacer(Modifier.height(8.dp))
                OutlinedButton(onClick = { typed = http; vm.connect(http, noAnswer, notServer) }, enabled = !vm.setupBusy,
                    modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.try_http, http)) }
            }
        }
    }
}

@Composable
fun PairScreen(vm: AppViewModel) {
    val expired = stringResource(R.string.code_expired)
    val network = stringResource(R.string.network_retry)
    LaunchedEffect(Unit) { vm.startPairing(expired, network) }
    DisposableEffect(Unit) { onDispose { vm.stopPairing() } }
    Centered {
        Logo()
        Text(stringResource(R.string.enter_code), style = MaterialTheme.typography.titleMedium)
        Text(
            vm.pairCode.ifEmpty { "······" }, fontFamily = FontFamily.Monospace, fontSize = 64.sp,
            fontWeight = FontWeight.Bold, letterSpacing = 8.sp, modifier = Modifier.padding(vertical = 16.dp),
        )
        Text(stringResource(R.string.code_help), color = Muted, textAlign = TextAlign.Center,
            modifier = Modifier.widthIn(max = 560.dp))
        Spacer(Modifier.height(8.dp))
        Text(vm.pairNote ?: stringResource(R.string.waiting_approval), color = Muted)
        Spacer(Modifier.height(24.dp))
        OutlinedButton(onClick = { vm.changeServer() }) { Text(stringResource(R.string.change_address)) }
    }
}

@Composable
fun StartScreen(vm: AppViewModel) {
    val ended = stringResource(R.string.session_ended)
    val network = stringResource(R.string.network_retry)
    LaunchedEffect(Unit) { vm.start(ended, network) }
    Centered {
        Logo()
        CircularProgressIndicator()
        Spacer(Modifier.height(16.dp))
        Text(vm.startNote ?: stringResource(R.string.connecting), color = Muted)
        Spacer(Modifier.height(24.dp))
        TextButton(onClick = { vm.changeServer() }) { Text(stringResource(R.string.change_address)) }
    }
}

@Composable
private fun SettingRow(label: String, value: String) {
    Row(modifier = Modifier.fillMaxWidth().padding(vertical = 14.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label)
        Text(value, color = Muted)
    }
    HorizontalDivider(color = NavyLight)
}

@Composable
fun SettingsScreen(vm: AppViewModel) {
    val intervals = listOf(3, 5, 8, 12, 20, 30)
    var interval by remember { mutableStateOf(vm.store.interval) }
    Column(modifier = Modifier.fillMaxSize().padding(24.dp).widthIn(max = 640.dp)) {
        Text(stringResource(R.string.settings), style = MaterialTheme.typography.headlineSmall,
            modifier = Modifier.padding(bottom = 16.dp))
        SettingRow(stringResource(R.string.server), vm.store.server)
        SettingRow(stringResource(R.string.signed_in_as), vm.user.ifEmpty { "–" })
        Row(modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp), horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically) {
            Text(stringResource(R.string.slideshow_interval))
            Row(verticalAlignment = Alignment.CenterVertically) {
                TextButton(onClick = {
                    val i = intervals.indexOf(interval).let { if (it < 0) 2 else it }
                    interval = intervals[(i - 1 + intervals.size) % intervals.size]; vm.store.interval = interval
                }) { Text("−", fontSize = 22.sp) }
                Text(stringResource(R.string.seconds, interval), color = Amber)
                TextButton(onClick = {
                    val i = intervals.indexOf(interval).let { if (it < 0) 2 else it }
                    interval = intervals[(i + 1) % intervals.size]; vm.store.interval = interval
                }) { Text("+", fontSize = 22.sp) }
            }
        }
        HorizontalDivider(color = NavyLight)
        SettingRow(stringResource(R.string.app_version), BuildConfig.VERSION_NAME)
        Spacer(Modifier.height(24.dp))
        OutlinedButton(onClick = { vm.signOut() }, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.sign_out)) }
        Spacer(Modifier.height(12.dp))
        OutlinedButton(onClick = { vm.changeServer() }, modifier = Modifier.fillMaxWidth()) { Text(stringResource(R.string.change_server)) }
    }
}
