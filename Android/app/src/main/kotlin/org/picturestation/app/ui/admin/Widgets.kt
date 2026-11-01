// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.ui.admin

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.picturestation.app.R
import org.picturestation.app.data.Grant
import org.picturestation.app.ui.Amber
import org.picturestation.app.ui.Danger
import org.picturestation.app.ui.Muted
import org.picturestation.app.ui.Navy
import org.picturestation.app.ui.NavyLight
import org.picturestation.app.ui.Paper

/** The building blocks of the administration screens, after the web gallery's Settings: cards, tags, chips,
 *  forms and confirmations in the app's colours (amber = administrator, allowed, public; red = disabled, excluded). */

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AdminScaffold(title: String, onBack: () -> Unit, content: @Composable (PaddingValues) -> Unit) {
    Scaffold(
        containerColor = Navy,
        topBar = {
            TopAppBar(
                title = { Text(title, maxLines = 1) },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.back)) } },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Navy, titleContentColor = Paper, navigationIconContentColor = Paper),
            )
        },
        content = content,
    )
}

@Composable
fun AdminCard(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Column(modifier = modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(NavyLight).padding(12.dp), content = content)
}

enum class TagKind { ACCENT, BAD, PLAIN }

@Composable
fun Tag(text: String, kind: TagKind = TagKind.PLAIN) {
    val bg = when (kind) { TagKind.ACCENT -> Amber; TagKind.BAD -> Danger; TagKind.PLAIN -> Color.Transparent }
    val fg = when (kind) { TagKind.ACCENT -> Navy; TagKind.BAD -> Paper; TagKind.PLAIN -> Muted }
    Text(
        text, fontSize = 12.sp, color = fg,
        modifier = Modifier.clip(RoundedCornerShape(6.dp)).background(bg)
            .then(if (kind == TagKind.PLAIN) Modifier.border(1.dp, Muted, RoundedCornerShape(6.dp)) else Modifier)
            .padding(horizontal = 6.dp, vertical = 2.dp),
    )
}

@Composable
fun MutedText(text: String, modifier: Modifier = Modifier) { Text(text, color = Muted, fontSize = 13.sp, modifier = modifier) }

@Composable
fun SectionTitle(text: String) { Text(text, color = Paper, fontWeight = FontWeight.Bold, fontSize = 16.sp) }

@Composable
fun InlineError(msg: String?) {
    if (!msg.isNullOrEmpty()) Text(msg, color = Danger, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp))
}

@Composable
fun Spinner() {
    Box(modifier = Modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator(color = Paper) }
}

/** The list is still loading, failed, or has nothing in it. */
@Composable
fun EmptyOrError(loading: Boolean, error: String?, empty: String?, onRetry: (() -> Unit)? = null) {
    when {
        loading -> Spinner()
        error != null -> Column(modifier = Modifier.fillMaxWidth().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            Text(error, color = Danger)
            if (onRetry != null) TextButton(onClick = onRetry) { Text(stringResource(R.string.retry)) }
        }
        empty != null -> MutedText(empty, Modifier.padding(16.dp))
    }
}

@Composable
fun FormField(
    label: String, value: String, onChange: (String) -> Unit, modifier: Modifier = Modifier.fillMaxWidth(),
    password: Boolean = false, keyboardType: KeyboardType = KeyboardType.Text,
    capitalization: KeyboardCapitalization = KeyboardCapitalization.None, placeholder: String? = null,
    singleLine: Boolean = true, maxLength: Int = 0,
) {
    OutlinedTextField(
        value = value, onValueChange = { if (maxLength <= 0 || it.length <= maxLength) onChange(it) },
        label = { Text(label) }, placeholder = placeholder?.let { { Text(it, color = Muted) } },
        singleLine = singleLine, minLines = if (singleLine) 1 else 3,
        visualTransformation = if (password) PasswordVisualTransformation() else VisualTransformation.None,
        keyboardOptions = KeyboardOptions(keyboardType = if (password) KeyboardType.Password else keyboardType,
            capitalization = capitalization, autoCorrectEnabled = false),
        modifier = modifier,
    )
}

@Composable
fun CheckRow(label: String, checked: Boolean, onChange: (Boolean) -> Unit, hint: String? = null, enabled: Boolean = true) {
    Row(
        modifier = Modifier.fillMaxWidth().clickable(enabled = enabled) { onChange(!checked) }.padding(vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Checkbox(checked = checked, onCheckedChange = { onChange(it) }, enabled = enabled)
        Column { Text(label); hint?.let { MutedText(it) } }
    }
}

@Composable
fun RadioRow(label: String, hint: String?, selected: Boolean, onSelect: () -> Unit) {
    Row(modifier = Modifier.fillMaxWidth().clickable { onSelect() }.padding(vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
        RadioButton(selected = selected, onClick = onSelect)
        Column { Text(label); hint?.let { MutedText(it) } }
    }
}

/** A choice among a few labelled values: a button that opens a menu. */
@Composable
fun OptionPicker(label: String, options: List<Pair<String, String>>, value: String, modifier: Modifier = Modifier.fillMaxWidth(), onChange: (String) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Box(modifier) {
        OutlinedButton(onClick = { open = true }, modifier = Modifier.fillMaxWidth()) {
            Text("$label: " + (options.firstOrNull { it.first == value }?.second ?: value), color = Paper)
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            options.forEach { (v, l) -> DropdownMenuItem(text = { Text(l) }, onClick = { onChange(v); open = false }) }
        }
    }
}

@Composable
fun ConfirmDialog(text: String, confirmLabel: String, onConfirm: () -> Unit, onDismiss: () -> Unit, title: String? = null) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = title?.let { { Text(it) } },
        text = { Text(text) },
        confirmButton = { TextButton(onClick = { onDismiss(); onConfirm() }) { Text(confirmLabel, color = Danger) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text(stringResource(R.string.cancel)) } },
    )
}

/** The albums a user, group or guest may (or may not) see, as chips with a cross that removes the rule. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun GrantChips(grants: List<Grant>, emptyText: String, onRevoke: (Grant) -> Unit, onEdit: () -> Unit) {
    val allowed = grants.filter { !it.deny }
    val denied = grants.filter { it.deny }
    when {
        grants.isEmpty() -> MutedText(emptyText)
        grants.size > 40 -> {
            MutedText(stringResource(R.string.grants_many, allowed.size, denied.size))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                allowed.take(40).forEach { GrantChip(it, onRevoke) }
            }
        }
        else -> FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            allowed.forEach { GrantChip(it, onRevoke) }
            denied.forEach { GrantChip(it, onRevoke) }
        }
    }
    TextButton(onClick = onEdit, contentPadding = PaddingValues(horizontal = 4.dp)) { Text(stringResource(R.string.access_edit), color = Amber) }
}

@Composable
private fun GrantChip(g: Grant, onRevoke: (Grant) -> Unit) {
    val label = g.path.ifEmpty { stringResource(R.string.whole_library) }
    val color = if (g.deny) Danger else Amber
    Row(
        modifier = Modifier.clip(RoundedCornerShape(14.dp)).border(1.dp, color, RoundedCornerShape(14.dp))
            .padding(start = 10.dp, end = 2.dp, top = 2.dp, bottom = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, fontSize = 13.sp, color = if (g.deny) Muted else Paper,
            textDecoration = if (g.deny) TextDecoration.LineThrough else null)
        if (g.deny) { Spacer(Modifier.width(6.dp)); Tag(stringResource(R.string.grant_excluded), TagKind.BAD) }
        IconButton(onClick = { onRevoke(g) }, modifier = Modifier.size(28.dp)) {
            Icon(Icons.Filled.Close, stringResource(if (g.deny) R.string.grant_cancel_excl else R.string.grant_remove),
                modifier = Modifier.size(16.dp), tint = Muted)
        }
    }
}

/** "Whole library › 2024 › Trip": every part leads back up. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun Crumbs(path: String, onGo: (String) -> Unit) {
    val parts = if (path.isEmpty()) emptyList() else path.split('/')
    FlowRow(verticalArrangement = Arrangement.Center) {
        TextButton(onClick = { onGo("") }, contentPadding = PaddingValues(horizontal = 4.dp)) {
            Text(stringResource(R.string.whole_library), color = if (parts.isEmpty()) Paper else Amber)
        }
        parts.forEachIndexed { i, p ->
            Text("›", color = Muted, modifier = Modifier.padding(top = 10.dp))
            val target = parts.take(i + 1).joinToString("/")
            TextButton(onClick = { onGo(target) }, contentPadding = PaddingValues(horizontal = 4.dp)) {
                Text(p, color = if (i == parts.lastIndex) Paper else Amber)
            }
        }
    }
}
