{\rtf1\ansi\ansicpg1252\cocoartf2822
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fswiss\fcharset0 Helvetica;}
{\colortbl;\red255\green255\blue255;}
{\*\expandedcolortbl;;}
\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\pard\tx566\tx1133\tx1700\tx2267\tx2834\tx3401\tx3968\tx4535\tx5102\tx5669\tx6236\tx6803\pardirnatural\partightenfactor0

\f0\fs24 \cf0 import Foundation\
import StoreKit\
\
@MainActor\
final class StoreKitManager: ObservableObject \{\
    static let shared = StoreKitManager()\
\
    // 1) Update to your real product ID created in App Store Connect\
    static let proProductID = "pro.monthly"\
\
    @Published var products: [Product] = []\
    @Published var isPro: Bool = false\
    @Published var isLoading: Bool = false\
    @Published var lastError: String?\
\
    private var updatesTask: Task<Void, Never>?\
\
    init() \{\
        // Start listening for transaction updates immediately\
        updatesTask = listenForTransactions()\
        Task \{ await refreshProductsAndEntitlement() \}\
    \}\
\
    deinit \{ updatesTask?.cancel() \}\
\
    func refreshProductsAndEntitlement() async \{\
        isLoading = true\
        defer \{ isLoading = false \}\
\
        do \{\
            let storeProducts = try await Product.products(for: [Self.proProductID])\
            self.products = storeProducts.sorted(by: \{ $0.displayName < $1.displayName \})\
        \} catch \{\
            lastError = "Failed to fetch products: \\(error.localizedDescription)"\
        \}\
\
        await updateEntitlementFromTransactions()\
    \}\
\
    func purchasePro() async \{\
        guard let product = products.first(where: \{ $0.id == Self.proProductID \}) else \{\
            lastError = "Product not loaded"\
            return\
        \}\
        do \{\
            let result = try await product.purchase()\
            switch result \{\
            case .success(let verification):\
                let transaction = try checkVerified(verification)\
                await transaction.finish()\
                await updateEntitlementFromTransactions()\
            case .userCancelled:\
                break\
            case .pending:\
                break\
            @unknown default:\
                break\
            \}\
        \} catch \{\
            lastError = "Purchase failed: \\(error.localizedDescription)"\
        \}\
    \}\
\
    func restore() async \{\
        do \{\
            try await AppStore.sync()\
            await updateEntitlementFromTransactions()\
        \} catch \{\
            lastError = "Restore failed: \\(error.localizedDescription)"\
        \}\
    \}\
\
    // MARK: - Entitlement\
\
    private func checkVerified<T>(_ result: VerificationResult<T>) throws -> T \{\
        switch result \{\
        case .unverified(_, let error):\
            throw error ?? NSError(domain: "StoreKit", code: -1, userInfo: [NSLocalizedDescriptionKey: "Unverified transaction"])\
        case .verified(let safe):\
            return safe\
        \}\
    \}\
\
    private func listenForTransactions() -> Task<Void, Never> \{\
        Task.detached(priority: .background) \{ [weak self] in\
            for await update in Transaction.updates \{\
                do \{\
                    let transaction = try self?.checkVerified(update)\
                    await transaction?.finish()\
                    await self?.updateEntitlementFromTransactions()\
                \} catch \{\
                    await MainActor.run \{ self?.lastError = "Verification failed: \\(error.localizedDescription)" \}\
                \}\
            \}\
        \}\
    \}\
\
    private func hasActiveProEntitlement(_ transactions: [Transaction]) -> Bool \{\
        let now = Date()\
        for t in transactions \{\
            guard t.productID == Self.proProductID else \{ continue \}\
            if let exp = t.expirationDate \{\
                if exp > now && t.revocationDate == nil \{\
                    return true\
                \}\
            \} else if t.revocationDate == nil \{\
                // Non-consumable fallback\
                return true\
            \}\
        \}\
        return false\
    \}\
\
    private func currentEntitlementTransactions() async -> [Transaction] \{\
        var result: [Transaction] = []\
        for await ent in Transaction.currentEntitlements \{\
            if case .verified(let t) = ent \{ result.append(t) \}\
        \}\
        return result\
    \}\
\
    @MainActor\
    private func setIsPro(_ value: Bool) \{\
        if value != self.isPro \{\
            self.isPro = value\
            // Optional: persist locally\
            UserDefaults.standard.set(value, forKey: "isPro")\
        \}\
    \}\
\
    private func loadCachedIsPro() \{\
        let cached = UserDefaults.standard.bool(forKey: "isPro")\
        self.isPro = cached\
    \}\
\
    func updateEntitlementFromTransactions() async \{\
        // Use cached value immediately for snappy UI, then refresh\
        await MainActor.run \{ self.loadCachedIsPro() \}\
\
        let txs = await currentEntitlementTransactions()\
        let active = hasActiveProEntitlement(txs)\
        await MainActor.run \{ self.setIsPro(active) \}\
    \}\
\}}