// SPDX-License-Identifier: GPL-3.0-or-later
package org.picturestation.app.data

import android.content.Context
import android.util.Log
import androidx.annotation.OptIn
import androidx.media3.common.MediaItem
import androidx.media3.common.util.UnstableApi
import androidx.media3.database.StandaloneDatabaseProvider
import androidx.media3.datasource.DataSpec
import androidx.media3.datasource.cache.CacheDataSource
import androidx.media3.datasource.cache.CacheWriter
import androidx.media3.datasource.cache.LeastRecentlyUsedCacheEvictor
import androidx.media3.datasource.cache.SimpleCache
import androidx.media3.datasource.okhttp.OkHttpDataSource
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.io.File

/**
 * The motions of Live Photos (a few MB each) on disk, so that a clip near the focus or the photo in view is there
 * before it is needed. One cache for the process (SimpleCache allows one instance per folder), 100 MB, the least
 * recently used clips go first. The key is the clip's id, not its URL (the URL carries the session).
 * Ordinary videos never go through here.
 */
@OptIn(UnstableApi::class)
object LiveCache {
    private const val MAX_BYTES = 100L shl 20
    private const val MAX_CLIP = 25L shl 20      // a "Live Photo" bigger than this is not prefetched
    private var cache: SimpleCache? = null
    private var job: Job? = null

    @Synchronized
    fun get(ctx: Context): SimpleCache = cache ?: SimpleCache(
        File(ctx.applicationContext.cacheDir, "live"), LeastRecentlyUsedCacheEvictor(MAX_BYTES),
        StandaloneDatabaseProvider(ctx.applicationContext),
    ).also { cache = it }

    fun factory(ctx: Context, api: Api): CacheDataSource.Factory = CacheDataSource.Factory()
        .setCache(get(ctx))
        .setUpstreamDataSourceFactory(OkHttpDataSource.Factory(api.client))
        .setFlags(CacheDataSource.FLAG_IGNORE_CACHE_ON_ERROR)

    fun mediaItem(api: Api, liveId: String): MediaItem =
        MediaItem.Builder().setUri(api.videoUrl(liveId, "web")).setCustomCacheKey(liveId).build()

    @Volatile private var writer: CacheWriter? = null

    /** Downloads the given clips one after another, nearest first; a new call replaces the previous list.
     *  Parts already on disk are skipped by CacheWriter itself, without a request. */
    fun prefetch(ctx: Context, scope: CoroutineScope, api: Api, ids: List<String>) {
        job?.cancel()
        writer?.cancel()
        if (ids.isEmpty()) return
        val factory = factory(ctx, api)
        job = scope.launch(Dispatchers.IO) {
            for (id in ids) {
                if (!isActive) break
                try {
                    val spec = DataSpec.Builder().setUri(api.videoUrl(id, "web")).setKey(id).build()
                    lateinit var w: CacheWriter
                    w = CacheWriter(factory.createDataSource(), spec, null) { len, _, _ -> if (len > MAX_CLIP) w.cancel() }
                    writer = w
                    w.cache()
                } catch (e: Exception) {
                    Log.d("LiveCache", "prefetch $id: $e")   // cancelled, too big, or offline: the player loads it later
                } finally {
                    writer = null
                }
            }
        }
    }
}
