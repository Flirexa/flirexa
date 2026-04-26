# ANDROID_APP — SpongeBot VPN Android Application  @ANDROID_APP

> Read after: `CLIENT_PORTAL.md`
> Next: `ARCH_MAP.md`

---

## OVERVIEW

| Item | Value |
|------|-------|
| Source path | `/opt/vpnmanager/android-app/` |
| Package | `com.spongebot.vpn` |
| Min SDK | 24 (Android 7.0) |
| Target SDK | 34 |
| Version | 1.1.0 (code: 110) |
| Build type | Release (assembleRelease) |
| APK output | `ui/build/outputs/apk/release/ui-release-unsigned.apk` |
| APK on server | `/opt/spongebot/src/web/static/SpongeBot-v1.1.0.apk` |
| APK metadata | `/opt/spongebot/src/web/static/apk-version.json` |
| Theme | SpongeBob ocean (Bikini Bottom) |
| Admin Panel | 12 fragments + 12 adapters (full CRUD) |

---

## ARCHITECTURE

### Module Structure

```
android-app/
├── ui/src/main/java/com/spongebot/vpn/
│   ├── activity/
│   │   ├── MainActivity.kt        # ViewPager2 + BottomNav, auto update check
│   │   ├── LoginActivity.kt       # Email/password login + auto-config setup + admin mode
│   │   ├── AdminActivity.kt       # Admin panel: ViewPager2 + BottomNav (5 tabs)
│   │   ├── MainPagerAdapter.kt    # FragmentStateAdapter for 5 tabs
│   │   └── BaseActivity.kt        # WireGuard tunnel observer base
│   ├── api/
│   │   ├── ApiClient.kt           # Retrofit2 singleton, base URL from TokenManager
│   │   ├── AdminApiClient.kt      # Retrofit for admin API (port 10086), self-signed cert trust
│   │   ├── ApiService.kt          # Client API endpoints (interface)
│   │   ├── AdminApiService.kt     # Admin API endpoints (24+ methods)
│   │   ├── ApiModels.kt           # Client request/response data classes
│   │   ├── AdminApiModels.kt      # Admin data classes (15+)
│   │   └── TokenManager.kt        # JWT storage, serverUrl, isAdmin, adminToken, adminServerUrl
│   ├── ui/
│   │   ├── home/HomeFragment.kt   # Main VPN screen: connect button, bubble animations
│   │   ├── servers/ServersFragment.kt  # Server list
│   │   ├── devices/DevicesFragment.kt  # Device (config) management
│   │   ├── subscriptions/SubscriptionsFragment.kt  # Plans + subscription status
│   │   ├── settings/SettingsFragment.kt  # Settings + Check for Updates
│   │   └── admin/                  # ★ 24 files: 12 fragments + 12 adapters ★
│   │       ├── AdminDashboardFragment.kt   # Stats, revenue, health, servers, alerts
│   │       ├── AdminClientsFragment.kt     # Full CRUD: create, search, filters, edit, delete
│   │       ├── AdminClientAdapter.kt       # Client cards with traffic bar, status badge
│   │       ├── AdminServersFragment.kt     # Start/Stop/Restart, bandwidth, clients, config
│   │       ├── AdminServerAdapter.kt       # Server cards with default badge, agent mode
│   │       ├── AdminUsersFragment.kt       # User list, search, navigate to detail
│   │       ├── AdminUserAdapter.kt         # User cards with tier badge
│   │       ├── AdminUserDetailFragment.kt  # 4 tabs: Info/Subscription/Devices/Payments
│   │       ├── AdminSubscriptionsFragment.kt # Tariff CRUD
│   │       ├── AdminTariffAdapter.kt       # Tariff cards with pricing
│   │       ├── AdminPaymentsFragment.kt    # Payment list, filters, confirm/reject
│   │       ├── AdminPaymentAdapter.kt      # Payment cards with status/actions
│   │       ├── AdminPromoCodesFragment.kt  # Promo code CRUD, stats
│   │       ├── AdminPromoCodeAdapter.kt    # Code display, toggle
│   │       ├── AdminTrafficRulesFragment.kt # Top consumers, rules CRUD
│   │       ├── AdminTrafficRuleAdapter.kt  # Rule display, toggle
│   │       ├── AdminSettingsFragment.kt    # Payment providers, SMTP, health
│   │       ├── AdminSupportFragment.kt     # Support tickets
│   │       ├── AdminTicketAdapter.kt       # Ticket display
│   │       ├── AdminLogsFragment.kt        # Audit log
│   │       ├── AdminLogAdapter.kt          # Log entries
│   │       ├── AdminBotsFragment.kt        # Bot management
│   │       ├── AdminMoreFragment.kt        # Navigation to sub-sections
│   │       └── AdminSubSectionFragment.kt  # Generic placeholder (legacy)
│   ├── model/
│   │   └── TunnelManager.kt       # WireGuard tunnel state machine
│   │       # selectTunnel() — set active tunnel without connecting
│   └── util/
│       ├── LocaleHelper.kt        # Language switching
│       └── UserKnobs.kt           # DataStore preferences (lastUsedTunnel, etc.)
└── ui/src/main/res/
    ├── font/
    │   ├── fredoka.xml             # Font family (BOTH android: and app: namespaces!)
    │   ├── fredoka_regular.ttf    # Static (fvar table removed)
    │   ├── fredoka_medium.ttf     # Static
    │   ├── fredoka_semibold.ttf   # Static
    │   └── fredoka_bold.ttf       # Static — default theme font
    ├── drawable/
    │   └── bg_bikini_bottom.*     # Ocean background image
    ├── layout/
    │   ├── activity_main_new.xml  # ViewPager2 + BottomNavigationView
    │   ├── activity_login.xml     # Login form
    │   ├── fragment_home.xml      # Connect button, status, stats cards
    │   ├── fragment_servers.xml   # Server list with ocean bg
    │   ├── fragment_devices.xml   # Device list with ocean bg
    │   ├── fragment_subscriptions.xml  # Subscription + plans
    │   └── fragment_settings.xml  # Settings + Updates card
    ├── values/
    │   ├── styles.xml             # AppThemeBase (fontFamily=fredoka_bold), SpongeBotNavIndicator
    │   ├── themes.xml             # WireGuardTheme extensions
    │   ├── colors.xml             # Full palette + spongebot_card_bg_alpha (#CCF5D76E)
    │   └── strings.xml            # All UI strings
    └── color/
        └── bottom_nav_colors.xml  # white active, 50% white inactive
```

---

## API INTEGRATION  @ANDROID_CFG

### Base URL
`TokenManager.DEFAULT_SERVER_URL = "https://203.0.113.1:10443/client-portal/"`
`TokenManager.DEFAULT_ADMIN_URL = "https://203.0.113.1/api/v1/"`
User can change in Settings → Advanced.

### API Endpoints (ApiService.kt)

| Method | Path | Description |
|--------|------|-------------|
| POST | `auth/login` | Login → access_token |
| POST | `auth/register` | Register |
| GET | `auth/me` | Current user info |
| GET | `wireguard/clients` | List user's WireGuard configs |
| GET | `wireguard/config/{id}` | Get config text |
| POST | `wireguard/create` | Create new WireGuard client |
| POST | `wireguard/auto-setup` | Auto-find/create config for this device |
| GET | `subscription` | Current subscription status |
| GET | `subscription/plans` | Available plans (from admin) |
| POST | `payments/create-invoice` | Create CryptoPay invoice |
| DELETE | `wireguard/clients/{id}` | Delete config |
| GET | `servers` | Available servers |
| GET | `version` | App version for update check |

---

## AUTO-CONFIG ON LOGIN  @ANDROID_CFG

### Flow (LoginActivity.kt → autoSetupAndGoToMain()):

```kotlin
1. api.login(email, password) → token stored in TokenManager
2. api.getMe() → verify user
3. api.autoSetup() → returns {client_id, config (WG .conf text), name}
4. Config.parse(BufferedReader(StringReader(body.config)))
5. tunnelManager.getTunnels().firstOrNull { it.name == body.name }
   → if exists: tunnel.setConfigAsync(config)  // update existing
   → else: tunnelManager.create(body.name, config)  // create new
6. tunnelManager.selectTunnel(tunnel)  // mark as active → HomeFragment sees it
7. goToMain()
```

### TunnelManager.selectTunnel() (added)
```kotlin
fun selectTunnel(tunnel: ObservableTunnel?) {
    lastUsedTunnel = tunnel  // private setter → updates UserKnobs + notifies observers
}
```

**Result:** User logs in → config auto-imported → HomeFragment shows tunnel → user taps Connect.

---

## UPDATES  @ANDROID_UPD

### Auto-check on launch (MainActivity.kt):

```kotlin
private fun checkForUpdatesSilently() {
    lifecycleScope.launch {
        delay(3000)  // wait for UI to settle
        val response = api.getVersion()
        if (response.body()!!.version_code > BuildConfig.VERSION_CODE) {
            showUpdateNotification(version, downloadUrl)  // push notification
        }
    }
}
```

### Push notification:
- Channel: `spongebot_updates`
- Icon: `ic_power`
- Tap → opens download URL in browser
- Requires `POST_NOTIFICATIONS` permission (Android 13+)

### Manual check (SettingsFragment.kt):
- "Check for Updates" button → calls `/version` → dialog if newer, text "Up to date" if same

### Version bump workflow (when releasing new build):
```
1. android-app/gradle.properties: wireguardVersionName=X.Y.Z, wireguardVersionCode=XYZ
2. Build APK: cd android-app && ./gradlew assembleRelease
3. Copy: cp android-app/ui/build/outputs/apk/release/*.apk src/web/static/SpongeBot-vX.Y.Z.apk
4. Update src/web/static/apk-version.json (version, version_code, filename, date, changelog)
5. Deploy to production (scp + restart spongebot-client-portal.service)
→ all users with older version_code get push notification on next launch
```

---

## UI & DESIGN  @ANDROID_UI

### Theme (SpongeBob / Bikini Bottom)

| Element | Value |
|---------|-------|
| Background | `bg_bikini_bottom` (ocean image) on ALL fragments |
| Overlay | `#40000000` (25% dark) over background |
| Primary color | `#FFD93D` (SpongeBob yellow) |
| Purple | `#9B59B6` |
| Card background | `#CCF5D76E` (yellow, 80% opaque = 20% transparent) |
| Font | Fredoka Bold (default), Fredoka family for variants |
| Bottom nav background | `#9B59B6` (purple) |
| Nav active indicator | `#9B59B6` (purple pill) |
| Nav icon active | `#FFFFFF` (white, 100%) |
| Nav icon inactive | `#80FFFFFF` (white, 50%) |
| Status bar | `#2A8BC7` (blue) |
| Nav bar | `#9B59B6` (purple) |

### CRITICAL: Font Setup

Fredoka font-family XML MUST have BOTH namespaces:

```xml
<!-- ui/src/main/res/font/fredoka.xml -->
<font-family xmlns:android="http://schemas.android.com/apk/res/android"
             xmlns:app="http://schemas.android.com/apk/res-auto">
    <font android:fontWeight="400" android:font="@font/fredoka_regular"
          app:fontWeight="400" app:font="@font/fredoka_regular" />
    ...
</font-family>
```

Why both:
- `android:` → used by API 26+ native resolver
- `app:` → used by AppCompat on API 24–25
- Only `app:` → font silently falls back to Roboto on API 26+

Font files MUST be static (no fvar/gvar/STAT/HVAR tables). Processing: `fonttools` to remove variable tables.

### Navigation (ViewPager2 + BottomNav)

5 tabs, swipeable:
```
0: Home (HomeFragment)       → R.id.nav_home
1: Servers (ServersFragment) → R.id.nav_servers
2: Plans (SubscriptionsFragment) → R.id.nav_subscriptions
3: Devices (DevicesFragment) → R.id.nav_devices
4: Settings (SettingsFragment) → R.id.nav_settings
```

Sync: ViewPager → BottomNav (`onPageSelected`), BottomNav → ViewPager (`setCurrentItem`).
`offscreenPageLimit = 4` — all fragments kept in memory.

### Animations (HomeFragment)

**Bubble burst** (on connect button press):
- 20–30 small circles explode outward from button center
- ObjectAnimator: translationX/Y + alpha fade
- DecelerateInterpolator

**Bubble rain** (while connected):
- Spawner: every 300–700ms, creates 2–5 bubbles
- Bubbles rise from bottom with random X, varying size/speed/alpha
- Continuous while `isConnected == true`

**Screen transitions:** ViewPager2 swipe with default page transform.

### Splash Screen

```xml
<!-- SplashTheme in styles.xml -->
<style name="SplashTheme" parent="AppTheme.NoActionBar">
    <item name="android:windowBackground">@drawable/bg_bikini_bottom</item>
</style>
```
LoginActivity uses SplashTheme, then calls `setTheme(AppTheme_NoActionBar)` in onCreate.

---

## BUILD

```bash
cd /opt/vpnmanager/android-app

# Full clean build
./gradlew clean assembleRelease

# Fast build (incremental)
./gradlew assembleRelease

# Output
ui/build/outputs/apk/release/ui-release-unsigned.apk  # ~20 MB

# Copy to static for distribution
cp ui/build/outputs/apk/release/*.apk ../src/web/static/SpongeBot-v1.1.0.apk
```

Build time: ~80s (clean), ~5-20s (incremental).

---

## KNOWN ISSUES / HISTORY

| Issue | Fix Applied |
|-------|-------------|
| Font not rendering | `fredoka.xml` had only `app:` namespace → API 26+ used Roboto. Fixed: added both namespaces |
| Variable fonts not loading | Removed fvar/gvar/STAT/HVAR tables with fontTools |
| App name "WireGuard β" | `ui/src/debug/res/values/strings.xml` overrode main. Fixed. |
| lastUsedTunnel not updating | `private set` — can't set from outside. Added `selectTunnel()` public method |
| APK download returned HTML | SPA catch-all intercepted `/download/app`. Fixed in `client_portal_main.py` |

---

*Tags: @ANDROID_APP @ANDROID_CFG @ANDROID_UPD @ANDROID_UI*
