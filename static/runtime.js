/* Shared URL and authenticated request boundary. The legacy root still works. */
(() => {
    'use strict';
    const config = JSON.parse(document.getElementById('labook-runtime').textContent);
    const prefix = config.prefix || '';
    if (prefix && !/^\/[A-Za-z0-9_.-]+(?:\/[A-Za-z0-9_.-]+)*$/.test(prefix)) {
        throw new Error('Invalid application prefix');
    }
    function url(path) {
        if (typeof path !== 'string' || !path.startsWith('/') || path.startsWith('//') || /[\\\x00-\x20\x7f]/.test(path)) {
            throw new Error('Invalid application URL');
        }
        const pathname = path.split(/[?#]/, 1)[0];
        if (/%(?:2f|5c|25)/i.test(pathname) || decodeURIComponent(pathname).split('/').some(x => x === '.' || x === '..')) {
            throw new Error('Invalid application URL');
        }
        return prefix + path;
    }
    let csrfPromise;
    async function csrf() {
        if (!csrfPromise) {
            csrfPromise = window.fetch(url('/_auth/session'), {credentials: 'same-origin', cache: 'no-store', redirect: 'error'})
                .then(async response => {
                    if (!response.ok) throw new Error('ログインの有効期限が切れました。画面を開き直してください。');
                    const session = await response.json();
                    if (!/^[a-f0-9]{64}$/.test(session.csrf || '')) throw new Error('ログイン状態を確認できません。');
                    return session.csrf;
                }).catch(error => { csrfPromise = undefined; throw error; });
        }
        return csrfPromise;
    }
    async function request(path, init = {}) {
        const target = url(path);
        const method = (init.method || 'GET').toUpperCase();
        const headers = new Headers(init.headers);
        if (config.gateway && !['GET', 'HEAD', 'OPTIONS'].includes(method)) {
            headers.set('X-LaBook-CSRF', await csrf());
        }
        const response = await window.fetch(target, {...init, method, headers, credentials: 'same-origin', redirect: 'error'});
        if (response.status === 401 || response.status === 403) csrfPromise = undefined;
        // A failed mutation is never replayed automatically.
        return response;
    }
    function shelfCode(value) {
        try {
            const parsed = new URL(value);
            if (!['https:', 'http:'].includes(parsed.protocol)) return null;
            for (const start of ['/L/', '/labook/L/', url('/L/')]) {
                if (parsed.pathname.startsWith(start)) {
                    const code = decodeURIComponent(parsed.pathname.slice(start.length));
                    if (code && !/[\/\\\x00-\x1f]/.test(code)) return code;
                }
            }
        } catch (_) { /* Ordinary search terms are not URLs. */ }
        return null;
    }
    async function logout() {
        try {
            const response = await request('/_auth/logout', {method: 'POST'});
            if (!response.ok && response.status !== 401) throw new Error('ログアウトを完了できませんでした。');
            window.location.assign(url('/_auth/logged-out'));
        } catch (error) { window.alert(error.message); }
    }
    function localNavigationTargets() {
        if (!config.localUrl) return false;
        let destination;
        let probe;
        try {
            const base = new URL(config.localUrl);
            if (!['http:', 'https:'].includes(base.protocol) || base.username || base.password
                || base.origin === window.location.origin) return false;
            const path = window.location.pathname;
            if (prefix && path !== prefix && !path.startsWith(prefix + '/')) return false;
            const relative = (prefix ? path.slice(prefix.length) : path).replace(/^\/+/, '');
            base.pathname = base.pathname.replace(/\/?$/, '/');
            base.search = ''; base.hash = '';
            probe = new URL('healthz', base);
            destination = new URL(relative, base);
            if (destination.origin !== base.origin) return false;
            destination.search = window.location.search;
            destination.hash = window.location.hash;
        } catch (_) { return false; }
        return {destination, probe};
    }
    function localDestinationUrl() {
        return localNavigationTargets()?.destination?.href || '';
    }
    async function reachableLocalDestination() {
        const targets = localNavigationTargets();
        if (!targets) return false;
        const {destination, probe} = targets;
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 10000);
        try {
            // Reachability only: opaque responses do not disclose local data.
            // Browsers may require local-network permission or block mixed content.
            await window.fetch(probe.href, {mode: 'no-cors', credentials: 'omit',
                cache: 'no-store', redirect: 'error', referrerPolicy: 'no-referrer',
                targetAddressSpace: 'local', signal: controller.signal});
            if (controller.signal.aborted) return false;
            return destination.href;
        } catch (_) { return false; }
        finally { clearTimeout(timeout); }
    }
    window.LaBook = Object.freeze({url, fetch: request, prefix, shelfCode, reachableLocalDestination, localDestinationUrl,
        logout, localUrl: config.localUrl || '', gateway: config.gateway === true});
})();
