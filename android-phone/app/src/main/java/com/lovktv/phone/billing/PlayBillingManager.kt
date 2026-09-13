package com.lovktv.phone.billing

import android.app.Activity
import com.android.billingclient.api.BillingClient
import com.android.billingclient.api.BillingClient.BillingResponseCode
import com.android.billingclient.api.BillingFlowParams
import com.android.billingclient.api.PendingPurchasesParams
import com.android.billingclient.api.ProductDetails
import com.android.billingclient.api.QueryProductDetailsParams
import com.android.billingclient.api.Purchase
import org.json.JSONArray
import org.json.JSONObject

/** Owns Play subscriptions and reports verified purchase tokens to the web app. */
class PlayBillingManager(private val activity: Activity, private val emit: (String) -> Unit) {
    private val products = linkedMapOf<String, ProductDetails>()
    private val client = BillingClient.newBuilder(activity)
        .setListener { result, purchases ->
            if (result.responseCode == BillingResponseCode.OK && purchases != null) {
                purchases.forEach { purchase -> handlePurchase(purchase) }
            } else if (result.responseCode != BillingResponseCode.USER_CANCELED) {
                emit(event("error", "code" to result.responseCode, "message" to result.debugMessage))
            }
        }
        .enablePendingPurchases(
            PendingPurchasesParams.newBuilder().enableOneTimeProducts().build()
        )
        .build()

    init { connect() }

    fun refresh(): String {
        if (!client.isReady) { connect(); return "{\"ready\":false}" }
        queryProducts()
        client.queryPurchasesAsync(
            com.android.billingclient.api.QueryPurchasesParams.newBuilder()
                .setProductType(BillingClient.ProductType.SUBS).build()
        ) { result, purchases ->
            if (result.responseCode == BillingResponseCode.OK) purchases.forEach { handlePurchase(it) }
        }
        return "{\"ready\":true}"
    }

    fun productsJson(): String {
        val list = JSONArray()
        products.forEach { (id, p) ->
            list.put(JSONObject().put("id", id).put("price", p.oneTimePurchaseOfferDetails?.formattedPrice ?: p.subscriptionOfferDetails?.firstOrNull()?.pricingPhases?.pricingPhaseList?.firstOrNull()?.formattedPrice.orEmpty()))
        }
        return JSONObject().put("ready", client.isReady).put("products", list).toString()
    }

    fun buy(productId: String): String {
        val details = products[productId] ?: return "{\"ok\":false,\"error\":\"product_not_ready\"}"
        val offer = details.subscriptionOfferDetails?.firstOrNull()
            ?: return "{\"ok\":false,\"error\":\"offer_not_found\"}"
        val params = BillingFlowParams.ProductDetailsParams.newBuilder()
            .setProductDetails(details).setOfferToken(offer.offerToken).build()
        val result = client.launchBillingFlow(activity, BillingFlowParams.newBuilder().setProductDetailsParamsList(listOf(params)).build())
        return JSONObject().put("ok", result.responseCode == BillingResponseCode.OK).put("code", result.responseCode).toString()
    }

    fun close() { client.endConnection() }

    private fun connect() {
        client.startConnection(object : com.android.billingclient.api.BillingClientStateListener {
            override fun onBillingSetupFinished(result: com.android.billingclient.api.BillingResult) {
                if (result.responseCode == BillingResponseCode.OK) { queryProducts(); refresh() }
                else emit(event("error", "code" to result.responseCode, "message" to result.debugMessage))
            }
            override fun onBillingServiceDisconnected() { emit(event("error", "code" to -1, "message" to "disconnected")) }
        })
    }

    private fun queryProducts() {
        val ids = listOf("starter_monthly", "pro_monthly")
        val list = ids.map { QueryProductDetailsParams.Product.newBuilder().setProductId(it).setProductType(BillingClient.ProductType.SUBS).build() }
        client.queryProductDetailsAsync(QueryProductDetailsParams.newBuilder().setProductList(list).build()) { result, detailsResult ->
            if (result.responseCode == BillingResponseCode.OK) {
                detailsResult.productDetailsList.forEach { products[it.productId] = it }
                emit(productsJson())
            }
        }
    }

    private fun handlePurchase(purchase: Purchase) {
        if (purchase.purchaseState != Purchase.PurchaseState.PURCHASED) return
        if (!purchase.isAcknowledged) client.acknowledgePurchase(
            com.android.billingclient.api.AcknowledgePurchaseParams.newBuilder().setPurchaseToken(purchase.purchaseToken).build()
        ) { }
        val product = purchase.products.firstOrNull() ?: return
        emit(event("purchase", "product_id" to product, "purchase_token" to purchase.purchaseToken, "order_id" to (purchase.orderId ?: "")))
    }

    private fun event(type: String, vararg pairs: Pair<String, Any?>): String {
        val o = JSONObject().put("type", type); pairs.forEach { o.put(it.first, it.second) }; return o.toString()
    }
}
