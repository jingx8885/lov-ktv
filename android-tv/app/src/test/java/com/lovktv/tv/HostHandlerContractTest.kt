package com.lovktv.tv

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Contract coverage for the split handler boundaries that do not need a device. */
class HostHandlerContractTest {
    @Test
    fun assetPathsKeepRootAndQueryCompatibility() {
        assertEquals("web/index.html", StaticAssetHandler.assetNameFor("/"))
        assertEquals("web/index.html", StaticAssetHandler.assetNameFor("/?v=abc"))
        assertEquals("web/js/app.js", StaticAssetHandler.assetNameFor("/js/app.js?v=abc"))
    }

    @Test
    fun mediaCachePolicyOnlyCachesSmallMetadataAssets() {
        assertTrue(MediaRequestHandler.shouldCacheName("song.json"))
        assertTrue(MediaRequestHandler.shouldCacheName("cover.jpg"))
        assertFalse(MediaRequestHandler.shouldCacheName("audio.m4a"))
    }

    @Test
    fun routingContractStillClassifiesLanAndProxyPaths() {
        assertEquals(ApiKind.Host, HostGateway.classify("/api/host"))
        assertEquals(ApiKind.Static, HostGateway.classify("/tv.html"))
        assertEquals(ApiKind.Proxy, HostGateway.classify("/api/apps"))
    }
}
