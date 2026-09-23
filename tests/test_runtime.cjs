const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/runtime.js', 'utf8');
function runtime(prefix, gateway, respond) {
    const calls = [];
    const context = {Headers, URL, document: {getElementById: () => ({textContent: JSON.stringify({prefix, gateway})})},
        window: {fetch: async (url, options) => { calls.push({url, options}); return respond(url, options); }}};
    vm.runInNewContext(source, context);
    return {api: context.window.LaBook, calls};
}
(async () => {
    for (const prefix of ['', '/labook', '/trial/index.php']) {
        const {api, calls} = runtime(prefix, false, () => new Response('{}'));
        assert.equal(api.url('/books?a=1&a=2'), prefix + '/books?a=1&a=2');
        for (const bad of ['https://outside.example/x', '//outside.example', '/a/../b', '/a%2fb', '/a\\b']) {
            assert.throws(() => api.url(bad));
        }
        assert.equal(api.shelfCode('https://old.example/L/A%20B'), 'A B');
        assert.equal(api.shelfCode('javascript:alert(1)'), null);
        const body = new FormData(); body.append('cover', new Blob(['test']), 'cover.jpg');
        await api.fetch('/books/100/cover', {method: 'POST', body});
        assert.equal(calls.length, 1);
        assert.equal(calls[0].options.body, body);
        assert.equal(calls[0].options.headers.has('X-LaBook-CSRF'), false);
    }
    const {api, calls} = runtime('/labook', true, url => new Response(
        JSON.stringify(url.endsWith('/_auth/session') ? {csrf: 'a'.repeat(64)} : {})));
    await Promise.all([api.fetch('/books', {method: 'POST'}), api.fetch('/users/1', {method: 'DELETE'})]);
    assert.equal(calls.filter(x => x.url.endsWith('/_auth/session')).length, 1);
    for (const call of calls.filter(x => !x.url.endsWith('/_auth/session'))) {
        assert.equal(call.options.headers.get('X-LaBook-CSRF'), 'a'.repeat(64));
        assert.equal(call.options.redirect, 'error');
    }
    const denied = runtime('/labook', true, url => new Response(
        JSON.stringify(url.endsWith('/_auth/session') ? {csrf: 'a'.repeat(64)} : {}),
        {status: url.endsWith('/_auth/session') ? 200 : 401}));
    assert.equal((await denied.api.fetch('/books', {method: 'POST'})).status, 401);
    assert.equal(denied.calls.length, 2, 'failed mutation must not be retried');
    const expired = runtime('/labook', true, () => new Response('{}', {status: 401}));
    await assert.rejects(expired.api.fetch('/books', {method: 'POST'}));
    assert.equal(expired.calls.length, 1, 'no mutation without a session token');
    console.log('Runtime URL, CSRF, multipart and no-retry tests passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
