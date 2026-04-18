/* Session leak guard.
 *
 * Defeats the back-forward cache (bfcache) so that pressing the browser's
 * Back button after logging out cannot repaint the previously-authenticated
 * view. Most browsers honour `Cache-Control: no-store` and skip bfcache
 * already, but Safari and some Firefox versions still cache pages even with
 * no-store unless the document has unloaded. This shim handles those cases.
 *
 * Strategy:
 *   1. On `pageshow`, if `event.persisted` is true the document came from
 *      bfcache. Force a real reload so the server-side session check runs.
 *   2. If the Navigation Timing API reports a back/forward navigation, reload
 *      once. Guarded by a sessionStorage flag so we don't loop.
 *
 * The Dash assets pipeline auto-loads any *.js in /assets/, alphabetically.
 * Naming this file with a leading underscore keeps it ahead of other shims
 * so it has a chance to bind listeners before Dash hydrates.
 */
(function () {
    "use strict";

    if (typeof window === "undefined") return;

    var FLAG = "__cpi_bfcache_reloaded__";

    function hardReload() {
        try {
            // replace() so the bfcache page does not stay in history.
            window.location.replace(window.location.href);
        } catch (_e) {
            window.location.reload();
        }
    }

    // 1) bfcache restoration — most reliable signal.
    window.addEventListener("pageshow", function (event) {
        if (event && event.persisted === true) {
            hardReload();
        }
    });

    // 2) back/forward navigation timing — covers the few browsers that don't
    //    set persisted=true but still serve a stale document.
    try {
        var navEntries = (window.performance && window.performance.getEntriesByType)
            ? window.performance.getEntriesByType("navigation")
            : [];
        var navType = navEntries.length ? navEntries[0].type : null;
        if (!navType && window.performance && window.performance.navigation) {
            // Legacy API: 2 == TYPE_BACK_FORWARD.
            navType = window.performance.navigation.type === 2 ? "back_forward" : null;
        }
        if (navType === "back_forward") {
            if (!window.sessionStorage.getItem(FLAG)) {
                window.sessionStorage.setItem(FLAG, "1");
                hardReload();
                return;
            }
        }
        // Clear the flag on any non-bfcache navigation so future Back presses
        // can trigger the guard again.
        window.sessionStorage.removeItem(FLAG);
    } catch (_e) {
        // sessionStorage / performance API unavailable — bfcache pageshow
        // listener above is still active, so we silently degrade.
    }
})();
