// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app

import android.app.Application
import android.os.Build
import android.util.Log
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.picturestation.app.data.Api
import org.picturestation.app.data.Item
import org.picturestation.app.data.Store

/** Where a Browse screen looks: the root, the newest photos, or an album. */
data class Where(val album: Item? = null, val latest: Boolean = false)

/** The list behind one Browse screen; kept while a deeper screen is open. */
class BrowseState(val where: Where) {
    val items = mutableStateListOf<Item>()
    var total by mutableIntStateOf(0)
    var loading by mutableStateOf(false)
    var error by mutableStateOf<String?>(null)
    var firstVisible by mutableIntStateOf(0)
    val media: List<Item> get() = items.filter { it.isMedia }
    fun mediaIndexOf(item: Item) = media.indexOf(item)
}

sealed class Screen {
    data object Setup : Screen()
    data object Pair : Screen()
    data object Start : Screen()
    data class Browse(val state: BrowseState) : Screen()
    data class Viewer(val state: BrowseState, val start: Int, val slideshow: Boolean) : Screen()
    data object Settings : Screen()
}

private const val TAG = "Picturestation"

class AppViewModel(app: Application) : AndroidViewModel(app) {
    val store = Store(app)
    val api = Api(store)
    val stack = mutableStateListOf<Screen>()
    var title by mutableStateOf("")
    var user by mutableStateOf("")
    var message by mutableStateOf<String?>(null)   // a short note for the user (toast)
    private var sortBy = "filename"
    private var sortDir = "asc"
    private var noTimeline = false
    var isTv = false
    private val page = 300

    init {
        title = store.title; user = store.user
        when {
            store.server.isEmpty() -> stack.add(Screen.Setup)
            store.sid.isEmpty() -> stack.add(Screen.Pair)
            else -> stack.add(Screen.Start)
        }
    }

    val current: Screen get() = stack.last()
    fun push(s: Screen) { stack.add(s) }
    fun pop(): Boolean { if (stack.size > 1) { stack.removeAt(stack.size - 1); return true }; return false }
    fun reset(s: Screen) { stack.clear(); stack.add(s) }

    val deviceName: String get() = (if (isTv) "Android TV " else "Android ") + (Build.MODEL ?: "")

    // ---------- server address ----------
    var setupBusy by mutableStateOf(false)
    var setupError by mutableStateOf<String?>(null)
    /** After https failed for a bare host: the http address the user may choose to try instead. */
    var setupHttpOffer by mutableStateOf<String?>(null)
    fun connect(typed: String, noAnswer: String, notServer: String) {
        val base = Api.normalize(typed) ?: run { setupError = noAnswer; return }
        setupBusy = true; setupError = null; setupHttpOffer = null
        viewModelScope.launch {
            try {
                if (api.isServer(base)) { store.server = base; store.sid = ""; setupBusy = false; reset(Screen.Pair); return@launch }
                setupError = notServer
            } catch (e: Api.ApiException) {
                setupError = if (e.kind == Api.Kind.NETWORK) noAnswer else notServer
                // https did not answer and the user typed no scheme: offer plain http, never switch silently
                if (e.kind == Api.Kind.NETWORK && base.startsWith("https://") && !typed.trim().startsWith("http"))
                    setupHttpOffer = "http://" + base.removePrefix("https://")
            }
            setupBusy = false
        }
    }

    // ---------- pairing ----------
    var pairCode by mutableStateOf("")
    var pairNote by mutableStateOf<String?>(null)
    private var pairJob: Job? = null
    fun startPairing(expiredNote: String, networkNote: String) {
        pairJob?.cancel()
        pairJob = viewModelScope.launch {
            var token = ""
            while (true) {
                if (token.isEmpty()) {
                    try {
                        val d = api.pairCode(deviceName)
                        token = d.optString("token"); pairCode = d.optString("code")
                    } catch (e: Api.ApiException) { pairNote = networkNote; delay(5000); continue }
                }
                delay(3000)
                val r = try { api.pairPoll(token) } catch (e: Api.ApiException) { pairNote = networkNote; continue }
                when (r.optString("status")) {
                    "ok" -> {
                        store.sid = r.optString("sid"); store.user = r.optString("username")
                        store.title = r.optString("title"); user = store.user; title = store.title
                        reset(Screen.Start); return@launch
                    }
                    "pending" -> pairNote = null
                    else -> { token = ""; pairNote = expiredNote }
                }
            }
        }
    }
    fun stopPairing() { pairJob?.cancel(); pairJob = null }

    // ---------- start with a saved session ----------
    var startNote by mutableStateOf<String?>(null)
    fun start(sessionEnded: String, networkNote: String) {
        viewModelScope.launch {
            while (true) {
                try {
                    val d = api.info()
                    title = d.optString("title", title); store.title = title
                    noTimeline = d.optBoolean("disable_timeline", false)
                    sortBy = d.optString("sort_by", "filename"); sortDir = d.optString("sort_direction", "asc")
                    val u = api.checkAuth()
                    if (u.isEmpty()) { store.sid = ""; pairNote = sessionEnded; reset(Screen.Pair); return@launch }
                    user = u; store.user = u
                    reset(Screen.Browse(BrowseState(Where())))
                    return@launch
                } catch (e: Api.ApiException) {
                    if (e.kind == Api.Kind.SESSION) { store.sid = ""; pairNote = sessionEnded; reset(Screen.Pair); return@launch }
                    startNote = networkNote; delay(5000)
                }
            }
        }
    }

    /** A lost session (the device was removed under Settings, TV) sends the app back to a new code. */
    private fun sessionLost(note: String) { store.sid = ""; pairNote = note; reset(Screen.Pair) }

    // ---------- lists ----------
    val showLatest get() = !noTimeline
    fun load(st: BrowseState, sessionEnded: String, passwordNote: String, failed: String, networkNote: String) {
        if (st.loading || (st.total > 0 && st.items.size >= st.total)) return
        st.loading = true; st.error = null
        viewModelScope.launch {
            try {
                Log.d(TAG, "list ${st.where} from ${st.items.size}")
                val (items, total) = if (st.where.latest) api.listLatest(st.items.size, page)
                else api.listAlbum(st.where.album?.id, st.items.size, page, sortBy, sortDir)
                Log.d(TAG, "list ${st.where}: ${items.size} items of $total")
                st.items.addAll(items); st.total = maxOf(total, st.items.size)
            } catch (e: Api.ApiException) {
                Log.w(TAG, "list ${st.where} failed: ${e.kind} ${e.code} ${e.message}")
                when (e.kind) {
                    Api.Kind.SESSION -> sessionLost(sessionEnded)
                    Api.Kind.NETWORK -> { st.error = networkNote; delay(5000); st.loading = false; load(st, sessionEnded, passwordNote, failed, networkNote); return@launch }
                    else -> st.error = if (e.kind == Api.Kind.API && e.code == 418) passwordNote else failed
                }
            }
            st.loading = false
        }
    }

    /** People and place of an item, fetched once. */
    private val detailCache = HashMap<String, Item>()
    suspend fun details(item: Item): Item? {
        detailCache[item.id]?.let { return it }
        return try { api.details(item.id)?.also { detailCache[item.id] = it } } catch (e: Api.ApiException) { null }
    }

    // ---------- settings ----------
    fun signOut() {
        viewModelScope.launch { api.logout(); store.sid = ""; store.user = ""; user = ""; reset(Screen.Pair) }
    }
    fun changeServer() { reset(Screen.Setup) }
}
