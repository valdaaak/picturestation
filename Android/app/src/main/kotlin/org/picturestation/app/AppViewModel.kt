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
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.picturestation.app.data.AdminApi
import org.picturestation.app.data.Api
import org.picturestation.app.data.Item
import org.picturestation.app.data.Store
import org.picturestation.app.data.Updater

/** Where a Browse screen looks: the root, the newest photos, an album, a page of the Collections
 *  (`coll`: root | people | tags | places, with `cc` the places of one country) or the photos of a tag,
 *  person, place or smart album (`group`). */
data class Where(val album: Item? = null, val latest: Boolean = false,
                 val coll: String? = null, val cc: String? = null, val country: String? = null, val group: Item? = null)

/** The lists behind the Collections, as the web gallery keeps them. */
class Collections(val smart: List<Item>, val tags: List<Item>, val places: List<Item>, val people: List<Item>, val at: Long)

/** The list behind one Browse screen; kept while a deeper screen is open. */
class BrowseState(val where: Where) {
    val items = mutableStateListOf<Item>()
    var total by mutableIntStateOf(0)
    var loading by mutableStateOf(false)
    var error by mutableStateOf<String?>(null)
    var firstVisible by mutableIntStateOf(0)
    var stale by mutableStateOf(false)   // reload when shown again (an album was renamed or got a new cover)
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
    data object Admin : Screen()                                                   // administration, tabs
    data class Access(val type: String, val name: String, val path: String) : Screen()   // access editor, one level
    data class AlbumAccess(val path: String) : Screen()                            // who sees an album
}

private const val TAG = "Picturestation"

/**
 * The app holds a list of paired galleries (Store.galleries) and shows one of them, the active one. Setup and Pair
 * work on `pendingBase`: a successful pairing adds or replaces that gallery and makes it active. That one flow
 * serves the first install, "Add gallery", a new code after a lost session, and "Change address".
 */
class AppViewModel(app: Application) : AndroidViewModel(app) {
    val store = Store(app)
    val api = Api(store)
    val adminApi = AdminApi(api)
    val stack = mutableStateListOf<Screen>()
    var galleries by mutableStateOf(store.galleries)
    var active by mutableIntStateOf(store.active)
    var title by mutableStateOf("")
    var user by mutableStateOf("")
    /** The gallery address Setup and Pair work on. */
    var pendingBase by mutableStateOf("")
    /** The paired user is an administrator of the active gallery (checkauth says so at the start). */
    var isAdmin by mutableStateOf(false)
    /** The administration is for phones and tablets; a TV remote cannot type names and passwords. */
    val showAdmin: Boolean get() = isAdmin && !isTv
    var admin by mutableStateOf<AdminState?>(null)
    var message by mutableStateOf<String?>(null)   // a short note for the user (toast)
    private var sortBy = "filename"
    private var sortDir = "asc"
    private var noTimeline = false
    var isTv = false
    private val page = 300

    init {
        sync()
        stack.add(if (galleries.isEmpty()) Screen.Setup else Screen.Start)
    }

    /** Mirrors the store into state after a change. */
    private fun sync() {
        galleries = store.galleries; active = store.active
        val g = store.current
        title = g?.title ?: ""; user = g?.user ?: ""
    }

    /** Indices of the paired galleries other than the active one: the tiles on the root screen. */
    val otherGalleries: List<Int> get() = galleries.indices.filter { it != active }

    val current: Screen get() = stack.last()
    fun push(s: Screen) { stack.add(s) }
    fun pop(): Boolean { if (stack.size > 1) { stack.removeAt(stack.size - 1); return true }; return false }
    fun reset(s: Screen) { stack.clear(); stack.add(s) }
    private fun replace(s: Screen) { stack.removeAt(stack.size - 1); stack.add(s) }

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
                if (api.isServer(base)) {
                    pendingBase = base; setupBusy = false
                    if (stack.size > 1) replace(Screen.Pair) else reset(Screen.Pair)
                    return@launch
                }
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

    /** Setup and Pair can be left when there is a screen below them (adding a gallery) or another gallery to show. */
    val canCancel: Boolean get() = stack.size > 1 || galleries.any { it.base != pendingBase && store.sidOf(it.base).isNotEmpty() }
    fun cancelSetup() {
        stopPairing()
        if (stack.size > 1) { pop(); return }
        val i = galleries.indexOfFirst { it.base != pendingBase && store.sidOf(it.base).isNotEmpty() }
        if (i >= 0) switchGallery(i)
    }
    fun changeAddress() {
        stopPairing()
        if (stack.size > 1) replace(Screen.Setup) else reset(Screen.Setup)
    }

    // ---------- pairing ----------
    var pairCode by mutableStateOf("")
    var pairNote by mutableStateOf<String?>(null)
    private var pairJob: Job? = null
    fun startPairing(expiredNote: String, networkNote: String) {
        pairJob?.cancel()
        pairCode = ""
        val base = pendingBase
        pairJob = viewModelScope.launch {
            var token = ""
            while (true) {
                if (token.isEmpty()) {
                    try {
                        val d = api.pairCode(deviceName, base)
                        token = d.optString("token"); pairCode = d.optString("code")
                    } catch (e: Api.ApiException) { pairNote = networkNote; delay(5000); continue }
                }
                delay(3000)
                val r = try { api.pairPoll(token, base) } catch (e: Api.ApiException) { pairNote = networkNote; continue }
                when (r.optString("status")) {
                    "ok" -> {
                        val i = store.upsert(Store.Gallery(base, r.optString("username"), r.optString("title")))
                        store.setSid(base, r.optString("sid")); store.active = i
                        sync(); detailCache.clear(); collections = null
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
            val g = store.current ?: run { pendingBase = ""; reset(Screen.Setup); return@launch }
            pendingBase = g.base
            isAdmin = false; admin = null
            if (store.sidOf(g.base).isEmpty()) { reset(Screen.Pair); return@launch }
            while (true) {
                try {
                    val d = api.info()
                    val t = d.optString("title", g.title)
                    noTimeline = d.optBoolean("disable_timeline", false)
                    sortBy = d.optString("sort_by", "filename"); sortDir = d.optString("sort_direction", "asc")
                    val a = api.checkAuth()
                    if (a.username.isEmpty()) { sessionLost(sessionEnded); return@launch }
                    isAdmin = a.isAdmin
                    store.upsert(g.copy(user = a.username, title = t)); sync()
                    if (autoUpdate()) return@launch   // Android replaces the app now; the user opens the new version
                    reset(Screen.Browse(BrowseState(Where())))
                    return@launch
                } catch (e: Api.ApiException) {
                    if (e.kind == Api.Kind.SESSION) { sessionLost(sessionEnded); return@launch }
                    startNote = networkNote; delay(5000)
                }
            }
        }
    }

    /** A lost session (the device was removed under Settings, TV) sends the gallery back to a new code;
     *  the other galleries stay paired. */
    private fun sessionLost(note: String) {
        isAdmin = false; admin = null
        store.setSid(store.server, ""); pendingBase = store.server; pairNote = note; reset(Screen.Pair)
    }

    // ---------- galleries ----------
    fun switchGallery(i: Int) {
        if (i !in galleries.indices) return
        store.active = i; sync(); detailCache.clear(); collections = null
        isAdmin = false; admin = null
        reset(Screen.Start)
    }
    fun addGallery() { pendingBase = ""; setupError = null; setupHttpOffer = null; push(Screen.Setup) }
    fun removeGallery(i: Int) {
        val g = galleries.getOrNull(i) ?: return
        val sid = store.sidOf(g.base)
        if (sid.isNotEmpty()) viewModelScope.launch { api.logout(g.base, sid) }   // the server forgets the device
        val wasActive = i == active
        store.remove(i); sync()
        if (galleries.isEmpty()) { pendingBase = ""; reset(Screen.Setup) }
        else if (wasActive) switchGallery(store.active)
    }

    // ---------- lists ----------
    val showLatest get() = !noTimeline
    fun load(st: BrowseState, sessionEnded: String, passwordNote: String, failed: String, networkNote: String) {
        if (st.loading || (st.total > 0 && st.items.size >= st.total)) return
        st.loading = true; st.error = null
        viewModelScope.launch {
            try {
                Log.d(TAG, "list ${st.where} from ${st.items.size}")
                val w = st.where
                val (items, total) = when {
                    w.group != null -> api.listGroup(w.group.id, st.items.size, page)
                    w.coll != null -> collectionPage(w).let { it to it.size }
                    w.latest -> api.listLatest(st.items.size, page)
                    else -> api.listAlbum(w.album?.id, st.items.size, page, sortBy, sortDir)
                }
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

    // ---------- collections: smart albums, people, tags, places (the web's Collections tab) ----------
    private var collections: Collections? = null
    private suspend fun collections(fresh: Boolean): Collections {
        collections?.let { if (!fresh && System.currentTimeMillis() - it.at < 60_000) return it }
        suspend fun part(block: suspend () -> List<Item>): List<Item> =
            try { block() } catch (e: Api.ApiException) { if (e.kind == Api.Kind.API) emptyList() else throw e }
        return Collections(part { api.smartAlbums() }, part { api.tags("desc") }, part { api.tags("geo") },
            part { api.tags("people") }, System.currentTimeMillis()).also { collections = it }
    }

    /** One page of the Collections as tiles. The root: the smart albums, then People, Tags and Places (each with
     *  the cover of its biggest entry); tags by name; places by country and then by the number of photos. */
    private suspend fun collectionPage(w: Where): List<Item> {
        val app = getApplication<Application>()
        val c = collections(fresh = w.coll == "root")
        fun tile(kind: String, title: String, of: List<Item>, n: Int, cc: String? = null) = Item(
            id = "coll:$kind" + (cc?.let { ":$it" } ?: ""), type = "coll", name = kind, title = title, taken = null,
            hasThumb = false, thumbMtime = null, sig = null, durationMs = 0, rotation = null, tvVersion = null, place = null,
            people = emptyList(), path = "", tags = emptyList(), count = n, cc = cc, country = cc?.let { title },
            cover = of.filter { it.hasThumb }.maxByOrNull { it.count })
        return when (w.coll) {
            "people" -> c.people
            "tags" -> c.tags.sortedWith(compareBy(java.text.Collator.getInstance()) { it.title })
            "places" -> if (w.cc == null) {
                c.places.groupBy { it.cc ?: "" }.entries.sortedByDescending { e -> e.value.sumOf { it.count } }
                    .map { (cc, list) -> tile("places", list.first().country ?: cc, list, list.size, cc) }
            } else c.places.filter { (it.cc ?: "") == w.cc }.sortedByDescending { it.count }
                .map { it.copy(title = it.title.substringBefore(", ")) }
            else -> c.smart + listOfNotNull(
                if (c.people.isNotEmpty()) tile("people", app.getString(R.string.people), c.people, c.people.size) else null,
                tile("tags", app.getString(R.string.tags), c.tags, c.tags.size),
                if (c.places.isNotEmpty()) tile("places", app.getString(R.string.places), c.places, c.places.map { it.cc ?: "" }.distinct().size) else null)
        }
    }

    /** People and place of an item, fetched once (ids are per gallery: cleared on a switch). */
    private val detailCache = HashMap<String, Item>()
    suspend fun details(item: Item): Item? {
        detailCache[item.id]?.let { return it }
        return try { api.details(item.id)?.also { detailCache[item.id] = it } } catch (e: Api.ApiException) { null }
    }
    fun forgetDetails(id: String) { detailCache.remove(id) }

    /** Prefetch the Live Photo motions around position [center] of [items] (nearest first, at most 10). */
    fun prefetchLive(items: List<Item>, center: Int, reach: Int = 8) {
        val ids = (0..reach).flatMap { listOf(center + it, center - it) }.distinct()
            .mapNotNull { i -> items.getOrNull(i)?.takeIf { it.type == "photo" }?.live }.distinct().take(10)
        org.picturestation.app.data.LiveCache.prefetch(getApplication(), viewModelScope, api, ids)
    }

    // ---------- administration (the web's Settings, over /api/admin) ----------
    fun openAdmin() {
        if (admin == null) admin = AdminState()
        push(Screen.Admin)
    }

    /** Fetches the gallery's state and the open tab's list; the screen shows `error` when it fails. */
    fun adminReload() { viewModelScope.launch { adminLoad() } }
    private suspend fun adminLoad() {
        val st = admin ?: return
        st.loading = true; st.error = null
        try {
            st.info = adminApi.state()
            adminLoadTabNow(st.tab, force = true)
        } catch (e: Exception) {
            st.error = adminFail(e, gate = true)
        }
        st.loading = false
    }

    /** The lists that are not part of `state`, loaded when their tab opens (or again after a change). */
    fun adminLoadTab(tab: AdminTab, force: Boolean = false) { viewModelScope.launch { adminLoadTabNow(tab, force) } }
    private suspend fun adminLoadTabNow(tab: AdminTab, force: Boolean) {
        val st = admin ?: return
        try {
            when (tab) {
                AdminTab.TV -> if (force || st.devices == null) st.devices = adminApi.deviceList()
                AdminTab.SHARES -> if (force || st.shares == null) st.shares = adminApi.shareList()
                AdminTab.MOVES -> if (force || st.moves == null) st.moves = adminApi.movesState()
                AdminTab.BEST -> if (force || st.best == null) st.best = adminApi.bestList()
                AdminTab.GALLERIES -> if (st.info?.isMain == true && (force || st.galleries == null)) st.galleries = adminApi.galleriesList()
                else -> {}
            }
        } catch (e: Exception) { adminFail(e) }
    }

    /** An administration action like the web's act(): run the op, say `ok`, reload; `onDone` gets the error text
     *  (null on success) so that a dialog can show it next to its fields. */
    fun adminRun(op: String, body: org.json.JSONObject, ok: String? = null, reload: Boolean = true, onDone: (String?) -> Unit = {}) {
        val st = admin ?: AdminState().also { admin = it }
        st.busy = true
        viewModelScope.launch {
            try {
                adminApi.post(op, body)
                ok?.let { message = it }
                if (reload) adminLoad()
                onDone(null)
            } catch (e: Exception) {
                onDone(adminFail(e))
            }
            st.busy = false
        }
    }

    /** A call with a result (access_view, album_get, ...); null and a toast when it fails. */
    suspend fun <T> adminFetch(block: suspend AdminApi.() -> T): T? =
        try { block(adminApi) } catch (e: Exception) { adminFail(e); null }

    /** Turns an administration error into the message to show; a lost session goes to a new code, a gatekeeper
     *  403 (`state`) hides the administration (the user is no administrator any more). */
    private fun adminFail(e: Exception, gate: Boolean = false): String {
        val app = getApplication<Application>()
        val msg = when {
            e is Api.ApiException && e.kind == Api.Kind.SESSION -> { sessionLost(app.getString(R.string.session_ended)); return "" }
            e is Api.ApiException && e.kind == Api.Kind.NETWORK -> app.getString(R.string.err_no_answer)
            e is Api.ApiException && e.kind == Api.Kind.BAD -> app.getString(R.string.load_failed)
            e is Api.ApiException -> e.message ?: app.getString(R.string.load_failed)
            else -> e.toString()
        }
        if (gate && e is Api.ApiException && e.code == 403) {
            isAdmin = false; admin = null
            while (current is Screen.Admin || current is Screen.Access || current is Screen.AlbumAccess) pop()
        }
        message = msg
        return msg
    }

    /** Pops the access editor up to the level with `path` (the breadcrumbs). */
    fun popAccessTo(path: String) {
        while (stack.size > 1) {
            val c = current
            if (c !is Screen.Access || c.path == path) return
            pop()
        }
    }

    /** The gallery's name changed in the administration: the app shows the new one too. */
    fun setGalleryTitle(t: String) {
        val g = store.current ?: return
        store.upsert(g.copy(title = t)); sync()
    }

    /** After an album was renamed or got a new cover: the lists behind the open screens load again when shown. */
    fun markBrowseStale() { stack.forEach { (it as? Screen.Browse)?.state?.stale = true } }

    // ---------- updates from the server (/app/version.json) ----------
    var update by mutableStateOf<Updater.Info?>(null)     // a newer version on the server
    var updateNote by mutableStateOf<String?>(null)       // result of a check started by the user
    var updateBusy by mutableStateOf(false)
    private var updateChecked = false
    fun checkUpdate(byUser: Boolean, latestNote: String, noneNote: String) {
        if (!byUser && updateChecked) return
        updateChecked = true
        viewModelScope.launch {
            if (!byUser) delay(2500)  // not in the way of the first list
            val info = withContext(Dispatchers.IO) { Updater.check(api) }
            update = info?.takeIf { it.versionCode > BuildConfig.VERSION_CODE }
            if (byUser) updateNote = when { info == null -> noneNote; update == null -> latestNote; else -> null }
        }
    }

    /** At the start: a newer version on the server goes in by itself where Android allows it (12 and later,
     *  installs from this app allowed). True when the app is being replaced; otherwise the start goes on and
     *  a newer version, if any, waits in the banner. */
    private suspend fun autoUpdate(): Boolean {
        if (updateChecked) return false
        updateChecked = true
        val app = getApplication<Application>()
        val info = withContext(Dispatchers.IO) { Updater.check(api) }
        update = info?.takeIf { it.versionCode > BuildConfig.VERSION_CODE } ?: return false
        if (!Updater.canInstallSilently(app, api)) return false
        startNote = app.getString(R.string.update_installing, info!!.versionName)
        updateBusy = true
        val replaced = runInstall(app)
        updateBusy = false
        if (replaced) startNote = app.getString(R.string.update_installed)
        return replaced
    }

    /** Downloads and installs [update]; true when Android reported success (the app is about to be replaced). */
    private suspend fun runInstall(ctx: android.content.Context): Boolean {
        val info = update ?: return false
        val app = getApplication<Application>()
        val done = kotlinx.coroutines.CompletableDeferred<Pair<Boolean, String?>>()
        Updater.onResult = { ok, msg -> done.complete(ok to msg) }
        return try {
            val file = withContext(Dispatchers.IO) { Updater.download(ctx, api, info) }
            withContext(Dispatchers.IO) { Updater.install(app, file, silent = Updater.canInstallSilently(app, api)) }
            val (ok, msg) = kotlinx.coroutines.withTimeout(60_000) { done.await() }
            when {
                ok -> true
                msg != null -> { Log.w(TAG, "update failed: $msg"); message = app.getString(R.string.update_failed); false }
                else -> false   // the system asks the user in its own dialog
            }
        } catch (e: Exception) {
            Log.w(TAG, "update failed: $e"); message = app.getString(R.string.update_failed); false
        }
    }

    /** The Update button of the banner and of Settings. */
    fun installUpdate(ctx: android.content.Context) {
        val info = update ?: return
        val app = getApplication<Application>()
        if (!Updater.canInstall(ctx)) { message = app.getString(R.string.update_permission); Updater.openInstallPermission(ctx); return }
        if (updateBusy) return
        updateBusy = true
        updateNote = app.getString(R.string.update_installing, info.versionName)
        message = updateNote
        viewModelScope.launch {
            updateNote = if (runInstall(ctx)) app.getString(R.string.update_installed) else null
            updateBusy = false
        }
    }
}
